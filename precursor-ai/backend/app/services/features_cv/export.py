"""Exporters: COG, Parquet, NumPy stack, and a PyTorch Dataset INTERFACE behind a lazy optional import.

torch is never installed by this project and nothing here trains, runs or scores a model. `torch_dataset` only builds a
map-style Dataset over an exported table when torch happens to be importable; otherwise it raises
OptionalDependencyMissing. It is not exercised beyond that refusal.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
import rasterio.shutil  # noqa: F401  (rasterio.shutil.copy)
from affine import Affine

from app.services.features_cv.tiling import Normalisation
from app.services.features_cv.types import FeatureError, OptionalDependencyMissing, forbidden_names


def write_cog(path: Path, arr: np.ndarray, transform: Affine, crs: str, tags: dict[str, str] | None = None) -> Path:
    """Cloud-optimised GeoTIFF, float32, NaN nodata, CRS and transform preserved. Falls back to a tiled GeoTIFF only if
    the COG driver is unavailable (reported in the file tag `container`)."""
    if arr.ndim != 2:
        raise FeatureError("write_cog expects a 2-D array")
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    meta = dict(driver="GTiff", height=h, width=w, count=1, dtype="float32", crs=crs, transform=transform, nodata=np.nan)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "src.tif"
        with rasterio.open(tmp, "w", **meta) as ds:
            ds.write(arr.astype(np.float32, copy=False), 1)
            ds.update_tags(**{k: str(v) for k, v in (tags or {}).items()}, container="COG")  # tags first: editing a COG afterwards breaks its layout
        try:
            rasterio.shutil.copy(tmp, path, driver="COG", compress="DEFLATE")
        except Exception:  # driver missing in an old GDAL: keep a valid tiled GeoTIFF and say so
            with rasterio.open(tmp, "r+") as ds:
                ds.update_tags(container="GTiff-tiled")
            rasterio.shutil.copy(tmp, path, driver="GTiff", tiled=True, compress="DEFLATE")
    return path


def to_parquet(df: pd.DataFrame, path: Path) -> Path:
    bad = forbidden_names(list(df.columns))
    if bad:
        raise FeatureError(f"refusing to write columns that look like scores/predictions: {bad}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)
    return path


def to_numpy_stack(arrays: dict[str, np.ndarray], path: Path, normalisation: dict[str, Normalisation] | None = None) -> Path:
    """Stack same-shaped 2-D arrays into one float32 `.npz` (`data`, `names`); applies recorded normalisations when given."""
    if not arrays:
        raise FeatureError("nothing to export")
    names = sorted(arrays)
    shapes = {arrays[n].shape for n in names}
    if len(shapes) != 1:
        raise FeatureError(f"arrays have different shapes {sorted(shapes)}; no silent resampling")
    cols = [(normalisation[n].apply(arrays[n]) if normalisation and n in normalisation else arrays[n].astype(np.float32)) for n in names]
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, data=np.stack(cols).astype(np.float32), names=np.array(names))
    return path


def torch_dataset(table: pd.DataFrame, feature_columns: list[str], index_column: str = "sample_id") -> Any:
    """Map-style torch Dataset over a samples table (features as float32, NaN kept). Requires torch (not installed here)."""
    try:
        import torch  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:
        raise OptionalDependencyMissing("torch is not installed (and is not a project dependency); the PyTorch Dataset interface is unavailable") from exc
    missing = [c for c in feature_columns + [index_column] if c not in table.columns]
    if missing:
        raise FeatureError(f"columns not in the table: {missing}")
    bad = forbidden_names(feature_columns)
    if bad:
        raise FeatureError(f"feature columns look like scores/predictions: {bad}")

    class SampleDataset(torch.utils.data.Dataset):  # pragma: no cover  (torch is never installed here)
        def __init__(self) -> None:
            self.ids = table[index_column].tolist()
            self.x = torch.tensor(table[feature_columns].to_numpy(dtype=np.float32))

        def __len__(self) -> int:
            return len(self.ids)

        def __getitem__(self, i: int) -> dict[str, Any]:
            return {"sample_id": self.ids[i], "features": self.x[i]}

    return SampleDataset()

