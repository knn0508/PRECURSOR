"""LOS geometry from product metadata and two-geometry identifiability (skill v3, Phase 2).

Convention (declared, internal): ENU displacement u = [u_E, u_N, u_U] in mm; the LOS unit vector l points
from the ground TO the satellite; d_LOS = l . u is positive for motion TOWARD the satellite.
This matches, verified per file:
  * OPERA DISP-S1 `displacement`: "Positive values indicate apparent motion towards the platform."
  * OPERA DISP-S1-STATIC `line_of_sight_enu`: band descriptions "... unit vector (ground to satellite)".
  * NISAR GUNW radarGrid `losUnitVector{X,Y}`: "defined from the target to the sensor ... ENU".
No incidence angle or heading is hard-coded: vectors are read from the static layers / metadata cubes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "data/raw/opera_static"
OPERA_LOS_DESCRIPTIONS = ("East component of line of sight unit vector (ground to satellite)",
                          "North component of line of sight unit vector (ground to satellite)",
                          "Vertical component of line of sight unit vector (ground to satellite)")


class GeometryError(RuntimeError):
    pass


def static_path(frame: int | str, layer: str = "line_of_sight_enu") -> Path:
    return STATIC_DIR / f"OPERA_L3_DISP-S1-STATIC_F{frame}_20140403_S1A_v1.0_{layer}.tif"


def opera_los_on_grid(frame: int | str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """(3, H, W) ENU ground->satellite unit vectors of an OPERA frame on pixel-centre grid (x, y).

    The static layer must be on the same 30 m UTM lattice (checked: pixel centres must coincide exactly);
    otherwise a GeometryError is raised instead of resampling silently.
    """
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(static_path(frame)) as d:
        if tuple(d.descriptions) != OPERA_LOS_DESCRIPTIONS:
            raise GeometryError(f"unexpected band descriptions {d.descriptions}")
        t = d.transform
        col0 = (x[0] - (t.c + t.a / 2)) / t.a
        row0 = (y[0] - (t.f + t.e / 2)) / t.e
        if abs(col0 - round(col0)) > 1e-6 or abs(row0 - round(row0)) > 1e-6 or abs(t.a - (x[1] - x[0])) > 1e-6:
            raise GeometryError("static layer lattice does not coincide with the displacement grid")
        a = d.read(window=Window(int(round(col0)), int(round(row0)), len(x), len(y))).astype(np.float64)
        nod = d.nodata
    if nod is not None:
        a[:, np.all(a == nod, axis=0)] = np.nan
    check_unit(a)
    return a


def opera_layover_shadow(frame, x, y) -> np.ndarray:
    """Categorical layover/shadow mask (0 ok, 1 shadow, 2 layover, 3 both) read without resampling."""
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(static_path(frame, "layover_shadow_mask")) as d:
        t = d.transform
        col0 = int(round((x[0] - (t.c + t.a / 2)) / t.a)); row0 = int(round((y[0] - (t.f + t.e / 2)) / t.e))
        return d.read(1, window=Window(col0, row0, len(x), len(y)))


def check_unit(l: np.ndarray, tol: float = 5e-3) -> None:
    n = np.sqrt(np.nansum(np.asarray(l) ** 2, axis=0))
    ok = np.isfinite(n) & (n > 0)
    if ok.any() and np.nanmax(np.abs(n[ok] - 1)) > tol:
        raise GeometryError(f"LOS vectors not unit length (max |norm-1| = {np.nanmax(np.abs(n[ok] - 1)):.4f})")


def los_from_xy(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    """Complete a ground->sensor unit vector from its E/N components (U >= 0 for a sensor above ground)."""
    east, north = np.asarray(east, float), np.asarray(north, float)
    h = east ** 2 + north ** 2
    if np.nanmax(h) > 1 + 1e-6:
        raise GeometryError("E/N components exceed unit length")
    return np.stack([east, north, np.sqrt(np.clip(1 - h, 0, 1))])


def project(u_enu: np.ndarray, l: np.ndarray) -> np.ndarray:
    """LOS displacement d = l . u (positive toward the sensor). u, l: (3, ...) arrays."""
    return np.sum(np.asarray(u_enu) * np.asarray(l), axis=0)


def identifiability(A: np.ndarray, names=("east", "north", "up")) -> dict:
    """Rank, condition number, singular values and null space of a (k x 3) LOS matrix.

    With k LOS rows of rank r < 3, any u + c * n (n in the null space) gives identical observations,
    so the component of motion along n is NOT observable from these data at all.
    """
    A = np.atleast_2d(np.asarray(A, float))
    U, s, Vt = np.linalg.svd(A)
    rank = int(np.sum(s > 1e-9 * s[0]))
    null = Vt[rank:]
    out = {"k": A.shape[0], "rank": rank, "singular_values": s.tolist(),
           "condition_number": float(s[0] / s[rank - 1]) if rank else np.inf,
           "null_space": null.tolist(), "observable_3d": rank == 3}
    if rank < 3:
        n = null[0]
        out["null_direction"] = {k: float(v) for k, v in zip(names, n)}
    return out


def angle_deg(l1, l2) -> float:
    l1, l2 = np.asarray(l1, float), np.asarray(l2, float)
    return float(np.degrees(np.arccos(np.clip(l1 @ l2 / np.linalg.norm(l1) / np.linalg.norm(l2), -1, 1))))
