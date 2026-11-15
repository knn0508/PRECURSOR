"""Run the author's SAVED B0 model (E3 LSTM-TCN) on the processed OPERA stack. Nothing is retrained.

Inputs (all in <repo>/data/displacement_forecast/): processed/opera_F16940_stack.nc, processed/imerg_daily_aoi.csv,
artifacts/model.pt (state_dict), artifacts/scaler.npz (train-only mean/std + feat_idx), processed/static_terrain.npz (5 terrain layers on the
stack grid; created once from the public Copernicus GLO-30 DEM by `fetch_static_terrain`, which needs the user's approval because it reads
a remote file).

    python -m displacement_forecast.saved_model verify     # reproduce artifacts/forecast.tif and report the difference
    python -m displacement_forecast.saved_model forecast --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from . import models as M
from . import train as TT
from .dataset import Scaler, build_samples

BUNDLE = Path(__file__).resolve().parents[3] / "data" / "displacement_forecast"
STATIC_NAMES = ["elevation", "slope_deg", "aspect_sin", "aspect_cos", "curvature"]
LABEL = "RESEARCH / INFERRED / NOT A WARNING: LOS displacement-increment forecast, not a landslide probability."


def load_scaler(path: Path) -> tuple[Scaler, np.ndarray, list[str]]:
    z = np.load(path, allow_pickle=False)
    sc = Scaler()
    sc.xm, sc.xs, sc.sm, sc.sd = z["xm"], z["xs"], z["sm"], z["sd"]
    sc.ym, sc.ys = float(z["ym"]), float(z["ys"])
    return sc, z["feat_idx"].astype(int), [str(n) for n in z["feat_names"]]


def fetch_static_terrain(bundle: Path = BUNDLE) -> Path:
    """Reads one public Copernicus GLO-30 tile window (remote, no login) and caches the terrain layers. Call only with user approval."""
    import xarray as xr

    from .ancillary import dem_on_grid
    from .discovery import AOI

    st = xr.open_dataset(bundle / "processed" / "opera_F16940_stack.nc")
    terr = dem_on_grid(st.x.values, st.y.values, st.attrs["crs_wkt"], AOI("portuguese_bend_rpv", -118.380, 33.725, -118.320, 33.765))
    out = bundle / "processed" / "static_terrain.npz"
    np.savez(out, **{k: np.nan_to_num(terr[k]).astype(np.float32) for k in STATIC_NAMES}, source=np.array(terr["source"]))
    return out


def forecast_last(bundle: Path = BUNDLE, static: np.ndarray | None = None, device: str | None = None, horizon: float = 12.0) -> dict:
    """Forecast +12 d from the last acquisition. `static` [5,H,W]; default loads processed/static_terrain.npz. Returns grids q10/q50/q90 (NaN = no estimate)."""
    import xarray as xr

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    st = xr.open_dataset(bundle / "processed" / "opera_F16940_stack.nc")
    times = pd.DatetimeIndex(st.time.values)
    if static is None:
        p = bundle / "processed" / "static_terrain.npz"
        if not p.is_file():
            raise FileNotFoundError("static_terrain.npz missing: terrain layers come from the public Copernicus DEM (needs user approval, see fetch_static_terrain)")
        z = np.load(p)
        static = np.stack([z[k] for k in STATIC_NAMES]).astype(np.float32)
    rain = pd.read_csv(bundle / "processed" / "imerg_daily_aoi.csv", index_col=0, parse_dates=True).iloc[:, 0]
    sc, fidx, _ = load_scaler(bundle / "artifacts" / "scaler.npz")
    L = build_samples(st.cum_mm.values, st.valid.values, st.coherence.values, times, static, STATIC_NAMES, rain=rain, window=6,
                      horizon=horizon, min_valid_steps=4, pixel_stride=1, issue_indices=[len(times) - 1])
    net = M.build("lstm_tcn", L.X.shape[1], len(fidx), L.S.shape[1], False, 64, 0.1).to(device)
    net.load_state_dict(torch.load(bundle / "artifacts" / "model.pt", map_location=device))
    q, _, _ = TT.predict(net, L, sc, fidx, device)
    H, W = st.cum_mm.shape[1:]
    g = np.full((3, H, W), np.nan, np.float32)  # NaN = no reliable estimate, never zero
    g[:, L.pix[:, 0], L.pix[:, 1]] = q.T
    if not (st.y[0] > st.y[-1]):
        g = g[:, ::-1]
    return {"label": LABEL, "issue_time": str(L.issue_time.max())[:10], "device": device, "grid": g, "n_pixels": int(len(L.pix))}


def verify(bundle: Path = BUNDLE, **kw) -> dict:
    """Compare our run with the author's committed forecast.tif (band 2 = q50)."""
    import rasterio

    r = forecast_last(bundle, **kw)
    with rasterio.open(bundle / "artifacts" / "forecast.tif") as f:
        ref = f.read(2)
    g = r["grid"][1]
    both = np.isfinite(g) & np.isfinite(ref)
    import xarray as xr

    st = xr.open_dataset(bundle / "processed" / "opera_F16940_stack.nc")
    cum, v = st.cum_mm.values, st.valid.values
    last = np.where(v[-1] & v[-2], cum[-1] - cum[-2], np.nan)          # last observed 12-day increment
    m = np.isfinite(g) & np.isfinite(last)
    corr = float(np.corrcoef(g[m], last[m])[0, 1]) if m.sum() > 2 else None
    return {"corr_forecast_vs_last_observed_increment": corr, "forecast_q50_sd_mm": float(np.nanstd(g)),
            "issue_time": r["issue_time"], "device": r["device"], "pixels_compared": int(both.sum()),
            "nan_pattern_equal": bool((np.isfinite(g) == np.isfinite(ref)).all()),
            "max_abs_diff_mm": float(np.abs(g[both] - ref[both]).max()) if both.any() else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["verify", "forecast"])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.cmd == "verify":
        res = {**verify(), "what": "saved model.pt + scaler.npz rerun on the processed stack, compared with the author's forecast.tif (nothing retrained)"}
        (BUNDLE / "artifacts" / "reproduction.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res, indent=1))
    else:
        r = forecast_last()
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            np.save(a.out / "forecast_q10_q50_q90.npy", r["grid"])
        print(json.dumps({k: v for k, v in r.items() if k != "grid"}, indent=1))
