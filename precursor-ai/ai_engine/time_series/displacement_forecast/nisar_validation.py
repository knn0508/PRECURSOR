"""NISAR L2 GUNW metadata audit, AOI subsetting and correction status (skill v3, Phase 3).

Verified facts (file P05023 v1.0.11 spec 1.5.0, and ASF GUNW guide, read 2026-11-15):
  * unwrappedPhase: radians, 80 m posting. Coherence 80 m (also 20 m with the wrapped interferogram).
  * ionospherePhaseScreen (+ uncertainty) is a separate 80 m layer. ASF: "included in the product but not
    applied to the data layers within the GUNW product by default".
  * Wet/hydrostatic troposphere and solid-earth-tide phases are metadata-cube lookup tables. ASF: "These phase
    corrections, when available, are not removed from the interferometric data."
  * parameters/geocoding/*CorrectionApplied = True flags are described in the file as "applied to improve
    geolocation", i.e. pixel positioning, NOT subtraction from the phase. (results/cross_sensor_table.md
    read them as phase corrections; that reading is superseded.)
  * Phase -> LOS sign: NOT stated in file attributes or the ASF guide pages read. Signed displacement is
    therefore BLOCKED (`SIGN_STATUS = "unverified"`); only sign-free quantities are reported.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
SUBSET_DIR = ROOT / "data/raw/nisar_subsets"
SIGN_STATUS = "unverified"
G = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"
RG = "science/LSAR/GUNW/metadata/radarGrid"
ID = "science/LSAR/identification"
GEO = "science/LSAR/GUNW/metadata/processingInformation/parameters/geocoding"
ASF_GUNW_URL = "https://nisar-docs.asf.alaska.edu/gunw/"

CORRECTIONS = {   # name -> (layer path relative to file root, geolocation flag)
    "ionosphere": (f"{G}/HH/ionospherePhaseScreen", ["rangeIonosphericCorrectionApplied", "azimuthIonosphericCorrectionApplied"]),
    "wet_troposphere": (f"{RG}/wetTroposphericPhaseScreen", ["wetTroposphericCorrectionApplied"]),
    "hydrostatic_troposphere": (f"{RG}/hydrostaticTroposphericPhaseScreen", ["hydrostaticTroposphericCorrectionApplied"]),
    "solid_earth_tide": (f"{RG}/slantRangeSolidEarthTidesPhase", []),
}


def _s(v):
    v = v[()] if isinstance(v, h5py.Dataset) else v
    if isinstance(v, bytes):
        return v.decode()
    if isinstance(v, np.ndarray) and v.dtype.kind == "S":
        return [x.decode() for x in v.ravel()]
    return v.item() if hasattr(v, "item") and np.ndim(v) == 0 else v


def identification(f: h5py.File) -> dict:
    keys = ["granuleId", "compositeReleaseId", "productVersion", "productSpecificationVersion", "productType",
            "orbitPassDirection", "lookDirection", "trackNumber", "frameNumber", "processingDateTime",
            "referenceZeroDopplerStartTime", "secondaryZeroDopplerStartTime", "productDoi", "isGeocoded"]
    out = {k: _s(f[f"{ID}/{k}"]) for k in keys if f"{ID}/{k}" in f}
    out["center_frequency_hz"] = float(_s(f["science/LSAR/GUNW/grids/frequencyA/centerFrequency"]))
    out["wavelength_m"] = 299792458.0 / out["center_frequency_hz"]
    out["temporal_baseline_days"] = int(_s(f["science/LSAR/GUNW/metadata/orbit/temporalBaseline"]))
    out["unwrapped_phase_units"] = _s(f[f"{G}/HH/unwrappedPhase"].attrs["units"])
    out["unwrapped_phase_description"] = _s(f[f"{G}/HH/unwrappedPhase"].attrs["description"])
    out["phase_spacing_m"] = float(_s(f[f"{G}/xCoordinateSpacing"]))
    out["projection_epsg"] = int(_s(f[f"{G}/projection"]))
    return out


def correction_status(f: h5py.File) -> list[dict]:
    """present / applied-to-phase status of each correction, with the evidence used."""
    rows = []
    for name, (path, flags) in CORRECTIONS.items():
        fl = {k: (_s(f[f"{GEO}/{k}"]), _s(f[f"{GEO}/{k}"].attrs.get("description", b""))) for k in flags if f"{GEO}/{k}" in f}
        rows.append({
            "correction": name, "layer": path.split("/")[-1], "present": path in f,
            "applied_to_unwrappedPhase": "not_applied",
            "evidence": (f"ASF GUNW guide ({ASF_GUNW_URL}): provided as layer, not applied/removed by default; "
                         "unwrappedPhase description does not mention any correction"),
            "geolocation_flags": json.dumps({k: v[0] for k, v in fl.items()}),
            "geolocation_flag_meaning": "; ".join(sorted({v[1] for v in fl.values()})) or "n/a",
            "our_pipeline_applies": False,
        })
    return rows


def aoi_slices(x: np.ndarray, y: np.ndarray, epsg: int, aoi, pad: int = 1):
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    xs, ys = tr.transform([aoi.west, aoi.east, aoi.west, aoi.east], [aoi.south, aoi.south, aoi.north, aoi.north])
    ix = np.where((x >= min(xs)) & (x <= max(xs)))[0]; iy = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    if len(ix) == 0 or len(iy) == 0:
        raise ValueError("AOI outside this GUNW grid")
    return (slice(max(iy.min() - pad, 0), iy.max() + 1 + pad), slice(max(ix.min() - pad, 0), ix.max() + 1 + pad))


def read_aoi(f: h5py.File, aoi, cube_levels_m=(0.0, 500.0)) -> dict:
    """AOI window of the 80 m layers plus the nearest metadata-cube node at `cube_levels_m`. Values unaltered."""
    ident = identification(f)
    x, y = f[f"{G}/xCoordinates"][()], f[f"{G}/yCoordinates"][()]
    sy, sx = aoi_slices(x, y, ident["projection_epsg"], aoi)
    out = {"x": x[sx], "y": y[sy]}
    for k in ["unwrappedPhase", "coherenceMagnitude", "connectedComponents", "ionospherePhaseScreen",
              "ionospherePhaseScreenUncertainty"]:
        out[k] = f[f"{G}/HH/{k}"][sy, sx]
    out["mask"] = f[f"{G}/mask"][sy, sx]
    # Metadata cubes are chunked (1, 512, 512) per height: read only the cube node nearest the AOI centre at
    # the height levels bracketing the AOI terrain (cube_levels_m), shaped (n_levels, 1, 1). Reading all 20
    # levels of 6 cubes costs ~150-250 MB per remote granule; this costs ~1/10 of that.
    cx, cy = f[f"{RG}/xCoordinates"][()], f[f"{RG}/yCoordinates"][()]
    hh = f[f"{RG}/heightAboveEllipsoid"][()]
    lv = sorted({int(np.argmin(abs(hh - h))) for h in cube_levels_m})
    jx = int(np.argmin(abs(cx - out["x"].mean()))); jy = int(np.argmin(abs(cy - out["y"].mean())))
    for k in ["losUnitVectorX", "losUnitVectorY", "incidenceAngle", "wetTroposphericPhaseScreen",
              "hydrostaticTroposphericPhaseScreen", "slantRangeSolidEarthTidesPhase"]:
        out[f"cube_{k}"] = np.stack([f[f"{RG}/{k}"][i, jy:jy + 1, jx:jx + 1] for i in lv])
    out["cube_x"], out["cube_y"], out["cube_h"] = cx[jx:jx + 1], cy[jy:jy + 1], hh[lv]
    out["ident_json"] = json.dumps(ident, default=str)
    out["corrections_json"] = json.dumps(correction_status(f), default=str)
    return out


def subset_path(granule: str) -> Path:
    return SUBSET_DIR / f"{granule}.npz"


def fetch_subset(url: str, granule: str, aoi) -> Path:
    """Idempotent remote AOI subset via HTTP range reads (precursor.remote.RangeFile)."""
    out = subset_path(granule)
    if out.exists():
        return out
    from .remote import RangeFile
    SUBSET_DIR.mkdir(parents=True, exist_ok=True)
    rf = RangeFile(url, block=256 * 2**10)
    with h5py.File(io.BufferedReader(rf, buffer_size=2**18), "r") as f:
        d = read_aoi(f, aoi)
    d["bytes_fetched"] = rf.bytes_fetched; d["source_url"] = url
    tmp = out.with_suffix(".part.npz")
    np.savez_compressed(tmp, **d)
    tmp.replace(out)
    return out


def load_subset(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    d = {k: z[k] for k in z.files}
    d["ident"] = json.loads(str(d.pop("ident_json"))); d["corrections"] = json.loads(str(d.pop("corrections_json")))
    return d


def usable(d: dict, coh_min: float = 0.3) -> np.ndarray:
    """Pre-registered usability rule of the source note: finite phase, coherence >= 0.3, component > 0.
    'usable' is a measurability flag, NOT proof of correct phase, sign or geometry."""
    cc = d["connectedComponents"].astype(np.int64)
    return np.isfinite(d["unwrappedPhase"]) & (d["coherenceMagnitude"] >= coh_min) & (cc > 0) & (cc != 65535)


def nisar_los_at(d: dict, elev_m: float) -> np.ndarray:
    """Ground->sensor ENU unit vector at the AOI centre, cube layer nearest `elev_m`."""
    from .los_geometry import los_from_xy
    k = int(np.argmin(abs(d["cube_h"] - elev_m)))
    return los_from_xy(float(np.nanmean(d["cube_losUnitVectorX"][k])), float(np.nanmean(d["cube_losUnitVectorY"][k])))


def phase_magnitude_mm(phase_rad: np.ndarray, wavelength_m: float) -> np.ndarray:
    """Sign-free |LOS path change| = |phase| * lambda / (4 pi), mm. Allowed while the sign is unverified."""
    return np.abs(np.asarray(phase_rad, float)) * wavelength_m / (4 * np.pi) * 1000.0


def signed_los_mm(phase_rad, wavelength_m, sign_status: str = SIGN_STATUS, sign: int | None = None):
    """Signed LOS displacement. Refused unless the sign convention has been verified from documentation."""
    if sign_status != "verified" or sign is None:
        raise PermissionError("NISAR GUNW phase->LOS sign convention unverified; signed displacement blocked")
    from .physics_checks import phase_to_los_mm
    return phase_to_los_mm(phase_rad, wavelength_m, sign)


class DoubleCorrectionError(RuntimeError):
    pass


def apply_phase_corrections(phase: np.ndarray, layers: dict, status: dict, already: tuple = ()) -> tuple[np.ndarray, list]:
    """Subtract correction phases (radians, same grid) from unwrapped phase, each at most once.

    status: correction name -> 'not_applied' | 'applied' | 'unknown' (from correction_status for THIS file).
    Refuses a correction whose status is 'applied' (already in the data) or 'unknown', and refuses any name in
    `already` (applied earlier in our own pipeline). Subtraction in the phase domain needs no LOS sign.
    Returns (corrected_phase, list_of_applied_names).
    """
    out, done = np.asarray(phase, float).copy(), []
    for name, scr in layers.items():
        st = status.get(name, "unknown")
        if name in already or name in done:
            raise DoubleCorrectionError(f"{name} already applied in this pipeline")
        if st == "applied":
            raise DoubleCorrectionError(f"{name} is already applied in the product")
        if st != "not_applied":
            raise DoubleCorrectionError(f"{name} status {st!r}: refusing to correct without verified status")
        out = out - np.asarray(scr, float)
        done.append(name)
    return out, done
