"""Per-date / per-pixel quality audit of OPERA DISP-S1 AOI subsets (skill Step 1, P0).

Three observation classes are kept apart. They must never be merged:
  OBSERVED       finite displacement and recommended_mask == 1
  MASKED_FINITE  finite displacement but recommended_mask == 0 (a measured value the product flags as low quality)
  ABSENT         no finite displacement (no measurement)
Mask reason codes use only the layers we have locally. The product rule (recommended_mask attribute) is:
water OR connected_component == 0 OR (temporal_coherence < 0.6 AND phase_similarity < 0.3).
phase_similarity and water_mask are NOT in our subsets, so the reason codes are partial by construction.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

OBSERVED, MASKED_FINITE, ABSENT = 0, 1, 2
CLASS_NAMES = {OBSERVED: "observed", MASKED_FINITE: "masked_finite", ABSENT: "absent"}
# reason bits for MASKED_FINITE pixels (partial: no phase_similarity / water_mask locally)
R_CC0, R_LOW_TC, R_OTHER = 1, 2, 4
TC_THRESHOLD = 0.6   # from the product's recommended_mask attribute


def classify(disp: np.ndarray, rec_mask: np.ndarray) -> np.ndarray:
    """Observation class per element. A missing value is ABSENT, never zero motion."""
    fin = np.isfinite(disp)
    out = np.full(disp.shape, ABSENT, np.int8)
    out[fin & (rec_mask > 0.5)] = OBSERVED
    out[fin & ~(rec_mask > 0.5)] = MASKED_FINITE
    return out


def reason_codes(cls: np.ndarray, cc: np.ndarray, tc: np.ndarray) -> np.ndarray:
    """Bit codes explaining MASKED_FINITE pixels from locally available layers (0 elsewhere)."""
    code = np.zeros(cls.shape, np.int8)
    m = cls == MASKED_FINITE
    code[m & (cc == 0)] |= R_CC0
    code[m & np.isfinite(tc) & (tc < TC_THRESHOLD)] |= R_LOW_TC
    code[m & (code == 0)] |= R_OTHER          # needs phase_similarity / water_mask to explain
    return code


def load_raw_cube(manifest: pd.DataFrame, subset_dir: Path) -> dict:
    """Stack the per-granule AOI subsets (no chaining, no correction) in secondary-date order."""
    m = manifest.sort_values("secondary_dt").reset_index(drop=True)
    keys = ["displacement", "recommended_mask", "temporal_coherence", "estimated_phase_quality",
            "connected_component_labels", "persistent_scatterer_mask"]
    cube = {k: [] for k in keys}
    for r in m.itertuples():
        ds = xr.open_dataset(subset_dir / f"{r.granule_id}.nc", engine="h5netcdf")
        for k in keys:
            cube[k].append(ds[k].values.astype(np.float32) if k in ds else None)
        ds.close()
    out = {k: (np.stack(v) if all(x is not None for x in v) else None) for k, v in cube.items()}
    out["displacement_mm"] = out.pop("displacement") * 1000.0          # meters -> mm, explicit
    out["reference_dt"] = pd.to_datetime(m.reference_dt).dt.normalize().values
    out["secondary_dt"] = pd.to_datetime(m.secondary_dt).dt.normalize().values
    out["granule_id"] = m.granule_id.values
    return out


def region_timeline(cls: np.ndarray, code: np.ndarray, qa: dict, regions: dict, dates) -> pd.DataFrame:
    """One row per (date, region): class counts plus QA medians, with the denominators."""
    rows = []
    for t, d in enumerate(dates):
        for name, mask in regions.items():
            c = cls[t][mask]
            k = code[t][mask]
            row = dict(date=pd.Timestamp(d), region=name, n_pixels=int(mask.sum()),
                       n_observed=int((c == OBSERVED).sum()), n_masked_finite=int((c == MASKED_FINITE).sum()),
                       n_absent=int((c == ABSENT).sum()),
                       n_masked_cc0=int(((k & R_CC0) > 0).sum()), n_masked_low_tc=int(((k & R_LOW_TC) > 0).sum()),
                       n_masked_unexplained=int(((k & R_OTHER) > 0).sum()))
            for q in ("temporal_coherence", "estimated_phase_quality"):
                if qa.get(q) is not None:
                    v = qa[q][t][mask]
                    row[f"median_{q}"] = float(np.nanmedian(v)) if np.isfinite(v).any() else np.nan
            if qa.get("connected_component_labels") is not None:
                row["frac_cc0"] = float(np.mean(qa["connected_component_labels"][t][mask] == 0))
            rows.append(row)
    return pd.DataFrame(rows)
