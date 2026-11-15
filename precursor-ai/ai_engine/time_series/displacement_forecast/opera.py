"""OPERA DISP-S1 ingest: remote AOI subsetting, QA layers and reference chaining.

Each DISP-S1 granule holds LOS displacement of `secondary_dt` relative to
`reference_dt`. Consecutive granules can switch to a new reference date
("ministack" re-referencing), so a continuous series is rebuilt by adding the
cumulative value already known at the new reference date. A pixel missing at
that date cannot be chained and stays NaN for the rest of that segment.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from pyproj import CRS, Transformer

QA_VARS = ["recommended_mask", "temporal_coherence", "estimated_phase_quality",
           "connected_component_labels", "persistent_scatterer_mask"]


def _crs_of(ds: xr.Dataset) -> CRS:
    for name in ("spatial_ref", "crs"):
        if name in ds.variables:
            a = ds[name].attrs
            for key in ("crs_wkt", "spatial_ref"):
                if key in a:
                    return CRS.from_wkt(a[key])
            if "epsg_code" in a:
                return CRS.from_epsg(int(a["epsg_code"]))
    gm = ds["displacement"].attrs.get("grid_mapping")
    if gm and gm in ds.variables:
        return CRS.from_wkt(ds[gm].attrs["crs_wkt"])
    raise ValueError("could not find CRS in OPERA file")


def aoi_window(ds: xr.Dataset, aoi) -> dict:
    """Index slices of the projected grid covering the lon/lat AOI."""
    crs = _crs_of(ds)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = tr.transform([aoi.west, aoi.east, aoi.west, aoi.east],
                          [aoi.south, aoi.south, aoi.north, aoi.north])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    xsel = slice(x0, x1) if ds.x[0] < ds.x[-1] else slice(x1, x0)
    ysel = slice(y0, y1) if ds.y[0] < ds.y[-1] else slice(y1, y0)
    return {"x": xsel, "y": ysel}


def read_subset(fileobj, aoi) -> tuple[xr.Dataset, dict]:
    """Read displacement + QA layers inside the AOI from one granule."""
    root = xr.open_dataset(fileobj, engine="h5netcdf", decode_timedelta=False)
    win = aoi_window(root, aoi)
    keep = ["displacement"] + [v for v in QA_VARS if v in root.variables]
    sub = root[keep].sel(win).load()
    for v in list(sub.data_vars):
        if "time" in sub[v].dims:
            sub[v] = sub[v].isel(time=0)
    meta = {
        "crs_wkt": _crs_of(root).to_wkt(),
        "units": {v: root[v].attrs.get("units") for v in keep},
        "attrs": {v: {k: str(val) for k, val in root[v].attrs.items()} for v in keep},
        "qa_present": [v for v in QA_VARS if v in root.variables],
    }
    try:
        ident = xr.open_dataset(fileobj, engine="h5netcdf", group="identification")
        meta["identification"] = {k: str(ident[k].values) for k in ident.variables
                                  if ident[k].size == 1}
    except Exception as e:  # identification group is optional for our purposes
        meta["identification_error"] = repr(e)
    root.close()
    return sub, meta


def fetch_subsets(manifest: pd.DataFrame, aoi, out_dir: Path, fs, workers: int = 8,
                  progress=True) -> list[Path]:
    """Download AOI subsets for every granule (cached; restartable)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [r for r in manifest.itertuples() if not (out_dir / f"{r.granule_id}.nc").exists()]

    def work(r):
        tmp = out_dir / f"{r.granule_id}.nc.part"
        with fs.open(r.url, block_size=4 * 2**20, cache_type="readahead") as f:
            sub, meta = read_subset(f, aoi)
        sub.attrs["source_granule"] = r.granule_id
        sub.attrs["source_url"] = r.url
        sub.attrs["reference_dt"] = str(r.reference_dt)
        sub.attrs["secondary_dt"] = str(r.secondary_dt)
        sub.attrs["meta_json"] = json.dumps(meta)
        sub.to_netcdf(tmp, engine="h5netcdf")
        os.replace(tmp, out_dir / f"{r.granule_id}.nc")
        return r.granule_id

    errors = []
    if todo:
        it = None
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(work, r): r.granule_id for r in todo}
            if progress:
                from tqdm.auto import tqdm
                it = tqdm(as_completed(futs), total=len(futs), desc="OPERA subsets")
            for fu in (it or as_completed(futs)):
                try:
                    fu.result()
                except Exception as e:
                    errors.append((futs[fu], repr(e)))
    if errors:
        print(f"{len(errors)} granules failed (re-run to retry). First: {errors[0]}")
    return sorted(out_dir.glob("*.nc"))


def build_stack(manifest: pd.DataFrame, subset_dir: Path, mask_policy: str = "recommended",
                coherence_min: float | None = None) -> xr.Dataset:
    """Chain referenced displacements into one cumulative LOS series in mm.

    Returns Dataset(time, y, x) with:
      cum_mm     cumulative LOS displacement since the first reference date (mm)
      valid      bool, pixel passes QA at that date
      coherence  temporal coherence if present (else NaN)
    """
    m = manifest.sort_values("secondary_dt").reset_index(drop=True)
    first = xr.open_dataset(subset_dir / f"{m.granule_id[0]}.nc", engine="h5netcdf")
    units = json.loads(first.attrs["meta_json"])["units"]["displacement"]
    scale = {"meters": 1000.0, "meter": 1000.0, "m": 1000.0, "mm": 1.0, "millimeters": 1.0}.get(str(units).lower())
    if scale is None:
        raise ValueError(f"unexpected displacement units {units!r}; refusing to guess")
    ny, nx = first.sizes["y"], first.sizes["x"]
    coords = {"y": first.y.values, "x": first.x.values}
    crs_wkt = json.loads(first.attrs["meta_json"])["crs_wkt"]
    first.close()

    t0 = pd.Timestamp(m.reference_dt.min()).normalize()
    known = {t0: np.zeros((ny, nx), np.float32)}  # cumulative value at each date
    times, cum, valid, coh = [], [], [], []
    for r in m.itertuples():
        ds = xr.open_dataset(subset_dir / f"{r.granule_id}.nc", engine="h5netcdf")
        d = ds["displacement"].values.astype(np.float32) * scale
        ok = np.isfinite(d)
        if mask_policy == "recommended" and "recommended_mask" in ds:
            ok &= ds["recommended_mask"].values.astype(bool)
        c = ds["temporal_coherence"].values.astype(np.float32) if "temporal_coherence" in ds else np.full_like(d, np.nan)
        if coherence_min is not None and "temporal_coherence" in ds:
            ok &= c >= coherence_min
        ds.close()
        ref = pd.Timestamp(r.reference_dt).normalize()
        sec = pd.Timestamp(r.secondary_dt).normalize()
        if ref not in known:
            raise ValueError(f"reference {ref.date()} of {r.granule_id} not reachable from earlier dates")
        value = known[ref] + d  # NaN propagates if the reference value is unknown
        known[sec] = value
        times.append(sec)
        cum.append(np.where(ok, value, np.nan))
        valid.append(ok & np.isfinite(value))
        coh.append(c)
    out = xr.Dataset(
        {"cum_mm": (("time", "y", "x"), np.stack(cum)),
         "valid": (("time", "y", "x"), np.stack(valid)),
         "coherence": (("time", "y", "x"), np.stack(coh))},
        coords={"time": pd.DatetimeIndex(times), **coords},
        attrs={"crs_wkt": crs_wkt, "first_reference": str(t0.date()),
               "units": "mm (LOS; positive sign convention as in source product)",
               "mask_policy": mask_policy, "coherence_min": str(coherence_min)},
    )
    return out


def remove_common_mode(stack: xr.Dataset, train_end: str, stable_quantile: float = 0.3,
                       min_train_obs: int = 20, min_pixels: int = 50) -> tuple[xr.Dataset, pd.DataFrame]:
    """Subtract a per-date spatial offset estimated on stable pixels (standard InSAR re-referencing).

    Why: a long-wavelength atmospheric / orbital signal shifts every pixel of one date by
    roughly the same amount. A per-pixel model cannot predict it, and it inflates 12-day
    increments. Removing the median of stable pixels at each date leaves the local motion.

    Leakage control:
      - The stable set is chosen from the TRAIN period only (dates < train_end): pixels with
        >= min_train_obs valid dates whose |linear LOS rate| is in the lowest `stable_quantile`.
      - The offset at date t uses only pixels observed at date t, so it is available at issue time.
    Dates with fewer than `min_pixels` stable valid pixels are left unchanged (offset = NaN in report).
    """
    cum = stack.cum_mm.values.astype(np.float64)
    valid = stack.valid.values
    times = pd.DatetimeIndex(stack.time.values)
    tr = times < pd.Timestamp(train_end)
    if tr.sum() < 3:
        raise ValueError("need >= 3 training dates to choose stable pixels")
    t = ((times[tr] - times[0]).days.values.astype(np.float64))[:, None, None]
    y = np.where(valid[tr], cum[tr], np.nan)
    n = np.isfinite(y).sum(0)
    tm = np.nansum(np.where(np.isfinite(y), t, 0), 0) / np.maximum(n, 1)
    ym = np.nanmean(y, 0)
    dt = np.where(np.isfinite(y), t - tm, 0.0)
    slope = np.nansum(dt * (y - ym), 0) / np.maximum((dt ** 2).sum(0), 1e-9)   # mm/day
    eligible = (n >= min_train_obs) & np.isfinite(slope)
    if eligible.sum() < min_pixels:
        raise ValueError(f"only {int(eligible.sum())} pixels with >= {min_train_obs} train observations")
    thr = np.quantile(np.abs(slope[eligible]), stable_quantile)
    stable = eligible & (np.abs(slope) <= thr)

    offsets, counts = np.full(len(times), np.nan), np.zeros(len(times), int)
    out = cum.copy()
    for i in range(len(times)):
        sel = stable & valid[i] & np.isfinite(cum[i])
        counts[i] = int(sel.sum())
        if counts[i] >= min_pixels:
            offsets[i] = float(np.median(cum[i][sel]))
            out[i] = cum[i] - offsets[i]
    res = stack.copy()
    res["cum_mm"] = (stack.cum_mm.dims, out.astype(np.float32))
    res["stable_mask"] = (("y", "x"), stable)
    res.attrs.update(common_mode="median of train-period stable pixels subtracted per date",
                     stable_quantile=str(stable_quantile), stable_rate_max_mm_day=str(float(thr)),
                     n_stable_pixels=str(int(stable.sum())))
    report = pd.DataFrame({"time": times, "offset_mm": offsets, "n_stable_valid": counts})
    return res, report


def thin_to_cadence(manifest: pd.DataFrame, min_gap_days: float = 11.0) -> pd.DataFrame:
    """Keep a ~12-day acquisition cadence (Sentinel-1A/1C-only years already have it).

    Why: in two-satellite years (S1A+S1B 2019-2021, S1A+S1C 2025-) acquisitions arrive every 6 days.
    Thinning makes every input window span the same time (6 x 12 d) and matches the 12-day horizon.
    Granules whose secondary date is a later ministack reference date are always kept, so
    reference chaining in `build_stack` never breaks.
    """
    m = manifest.copy()
    m["_sec"] = pd.to_datetime(m.secondary_dt).dt.normalize()
    m = m.sort_values("_sec")
    refs = set(pd.to_datetime(m.reference_dt).dt.normalize())
    keep, last = [], None
    for idx, sec in zip(m.index, m["_sec"]):
        if sec in refs or last is None or (sec - last).days >= min_gap_days:
            keep.append(idx)
            last = sec
    return manifest.loc[keep].reset_index(drop=True)


def remove_elevation_tropo(stack: xr.Dataset, elevation: np.ndarray, train_end: str,
                           min_pixels: int = 200) -> tuple[xr.Dataset, pd.DataFrame]:
    """Remove the elevation-correlated (stratified) tropospheric delay. OPERA DISP-S1 v1 applies none.

    For every consecutive pair of dates, the increment on STABLE pixels (stack.stable_mask, chosen from the
    train period by `remove_common_mode`) is regressed on centred elevation. The per-pair slopes are
    accumulated into a coefficient C(t) (mm per m). Its secular linear trend is fitted on TRAIN dates only
    and removed, so only the date-to-date atmospheric part is corrected. A slow elevation-correlated
    trend could be real deformation (the landslide sits low on the slope), so it is not touched.
    Causal: C(t) uses data up to date t; the trend uses train dates only. Run after remove_common_mode.
    """
    if "stable_mask" not in stack:
        raise ValueError("run remove_common_mode first (needs stable_mask)")
    cum = stack.cum_mm.values.astype(np.float64)
    valid = stack.valid.values
    times = pd.DatetimeIndex(stack.time.values)
    stable = stack.stable_mask.values.astype(bool) & np.isfinite(elevation)
    ec = np.nan_to_num(elevation - np.median(elevation[stable]))
    inc = np.diff(cum, axis=0)
    ok = valid[1:] & valid[:-1] & np.isfinite(inc)
    s = np.zeros(len(inc))
    for t in range(len(inc)):
        m = stable & ok[t]
        if m.sum() >= min_pixels:
            s[t] = np.linalg.lstsq(np.c_[np.ones(m.sum()), ec[m]], inc[t][m], rcond=None)[0][1]
    C = np.concatenate([[0.0], np.cumsum(s)])
    td = (times - times[0]).days.values.astype(float)
    tr = times < pd.Timestamp(train_end)
    trend = np.polyfit(td[tr], C[tr], 1)
    C_hp = C - np.polyval(trend, td)
    res = stack.copy()
    res["cum_mm"] = (stack.cum_mm.dims, (cum - C_hp[:, None, None] * ec[None]).astype(np.float32))
    res.attrs.update(tropo="elevation-correlated delay removed (per-date, stable-pixel regression, high-passed)",
                     tropo_secular_trend_removed_mm_per_100m_per_yr=str(float(trend[0] * 365.25 * 100)))
    report = pd.DataFrame({"time": times, "elev_coef_mm_per_100m": C_hp * 100, "raw_cum_coef_mm_per_100m": C * 100})
    return res, report
