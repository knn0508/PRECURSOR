"""GUNW -> LOS displacement / coherence / velocity rasters, block by block.

Only runs when the inspection says displacement is scientifically supported by the file's own metadata.
The input file is opened read-only and never modified.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from app.services.insar import hdf
from app.services.insar.coherence import CoherenceAccumulator, valid_coherence_mask
from app.services.insar.outputs import BlockWriter, RunningStats, bounds_4326, to_cog
from app.services.insar.phase_to_displacement import (
    SIGN_CONVENTION, SIGN_CONVENTION_VERIFIED, phase_to_los_displacement_m,
)
from app.services.insar.storage import check_disk
from app.services.insar.types import (
    InspectionReport, OutputFile, ProcessingConfig, ProcessingError, ProcessingResult, ProductType,
)
from app.services.insar.velocity import IncompatibleProducts, interferogram_mean_velocity, temporal_baseline_days

Cancelled = type("Cancelled", (Exception,), {})


def select_layers(rep: InspectionReport, polarization: str | None) -> tuple[str, dict[str, str | None]]:
    layers = rep.metadata.get("layers") or {}
    if not layers:
        raise ProcessingError("no unwrapped-phase layer available")
    pol = polarization or sorted(layers)[0]
    if pol not in layers:
        raise ProcessingError(f"polarization {pol!r} not in file (available: {sorted(layers)})")
    return pol, layers[pol]


def process_gunw(
    path: Path,
    rep: InspectionReport,
    cfg: ProcessingConfig,
    *,
    out_dirs: dict[ProductType, Path],
    tmp_dir: Path,
    min_free_bytes: int,
    progress: Callable[[float], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ProcessingResult:
    if not rep.displacement_supported or rep.grid is None or rep.wavelength_m is None:
        raise ProcessingError("displacement conversion not supported by this file: " + "; ".join(rep.displacement_blockers))
    pol, layer = select_layers(rep, cfg.polarization)
    grid, lam = rep.grid, rep.wavelength_m
    result = ProcessingResult(warnings=list(rep.warnings))
    if cfg.polarization is None and len(rep.metadata.get("layers", {})) > 1:
        result.warnings.append(f"polarization not specified: {pol} used")

    do_velocity = cfg.compute_velocity
    baseline_days = None
    if do_velocity:
        try:
            baseline_days = temporal_baseline_days(rep.reference_time, rep.secondary_time)
        except IncompatibleProducts as exc:
            do_velocity = False
            result.warnings.append(f"velocity not computed: {exc}")

    tmp_dir.mkdir(parents=True, exist_ok=True)
    check_disk(tmp_dir, grid.width * grid.height * 4 * 3 * 2, min_free_bytes)  # <=3 float32 rasters, tmp + final

    tags_common = {
        "DATA_ORIGIN": rep.data_origin.value, "PRODUCT": rep.product_kind.value, "POLARIZATION": pol,
        "REFERENCE_TIME": rep.reference_time.isoformat() if rep.reference_time else "",
        "SECONDARY_TIME": rep.secondary_time.isoformat() if rep.secondary_time else "",
        "ORBIT_DIRECTION": rep.orbit_direction or "", "SOURCE_FILE": path.name,
        "SCIENTIFICALLY_VALIDATED": "false",
    }
    writers: dict[ProductType, BlockWriter] = {}
    tmp_files: dict[ProductType, Path] = {}

    def add(kind: ProductType, unit: str, extra_tags: dict[str, str]) -> None:
        tmp = tmp_dir / f"{kind.value.lower()}.tmp.tif"
        tmp_files[kind] = tmp
        writers[kind] = BlockWriter(tmp, grid, {**tags_common, "UNITS": unit, "PRODUCT_TYPE": kind.value, **extra_tags})

    has_coh = bool(layer.get("coherence")) and not any("coherenceMagnitude shape differs" in w for w in rep.warnings)
    disp_stats, vel_stats = RunningStats(), RunningStats()
    coh_acc = CoherenceAccumulator(threshold=cfg.coherence_threshold)
    masked_by_coh = masked_by_cc = 0
    add(ProductType.LOS_DISPLACEMENT, "mm", {
        "SIGN_CONVENTION": SIGN_CONVENTION, "SIGN_CONVENTION_VERIFIED": str(SIGN_CONVENTION_VERIFIED).lower(),
        "WAVELENGTH_M": f"{lam:.9g}", "COHERENCE_THRESHOLD": str(cfg.coherence_threshold),
        "NOTE": "LOS displacement relative to an unspecified reference; not 3D motion; not a risk prediction",
    })
    if has_coh:
        add(ProductType.COHERENCE, "dimensionless", {"NOTE": "coherence magnitude as delivered by the product"})
    if do_velocity:
        add(ProductType.LOS_VELOCITY, "mm/year", {
            "NOTE": f"mean over the interferogram temporal baseline ({baseline_days:.3f} d); not a time series",
        })

    try:
        with h5py.File(path, "r") as f:
            ph_ds = f[layer["unwrapped_phase"]]
            fill = hdf.fill_value_of(ph_ds)
            coh_ds = f[layer["coherence"]] if has_coh else None
            coh_fill = hdf.fill_value_of(coh_ds) if coh_ds is not None else None
            cc_ds = f[layer["connected_components"]] if (cfg.use_connected_components_mask and layer.get("connected_components")) else None
            if cfg.use_connected_components_mask and cc_ds is None:
                result.warnings.append("connected-components mask requested but not found: not applied")
            rows = max(1, int(cfg.block_rows))
            for r0 in range(0, grid.height, rows):
                if cancelled and cancelled():
                    raise Cancelled()
                r1 = min(grid.height, r0 + rows)
                ph = np.asarray(ph_ds[r0:r1, :], dtype=np.float64)
                bad = ~np.isfinite(ph)
                if fill is not None and np.isfinite(fill):
                    bad |= ph == fill
                coh_blk = None
                if coh_ds is not None:
                    coh_blk = np.asarray(coh_ds[r0:r1, :], dtype=np.float64)
                    ok_coh = coh_acc.update(coh_blk, coh_fill)
                    if cfg.coherence_threshold is not None:
                        low = ok_coh & (coh_blk < cfg.coherence_threshold)
                        # Unusable coherence is treated as "no quality info": kept, but counted/flagged by stats.
                        masked_by_coh += int((low & ~bad).sum())
                        bad |= low
                    cout = np.where(ok_coh, coh_blk, np.nan)
                    writers[ProductType.COHERENCE].write(r0, cout)
                if cc_ds is not None:
                    zero = np.asarray(cc_ds[r0:r1, :]) == 0
                    masked_by_cc += int((zero & ~bad).sum())
                    bad |= zero
                disp_mm = phase_to_los_displacement_m(np.where(bad, np.nan, ph), lam) * 1000.0
                writers[ProductType.LOS_DISPLACEMENT].write(r0, disp_mm)
                disp_stats.update(disp_mm)
                if do_velocity:
                    v = interferogram_mean_velocity(disp_mm, rep.reference_time, rep.secondary_time)
                    writers[ProductType.LOS_VELOCITY].write(r0, v)
                    vel_stats.update(v)
                if progress:
                    progress(r1 / grid.height)
    finally:
        for w in writers.values():
            w.close()

    bounds = bounds_4326(grid)
    unit_of = {ProductType.LOS_DISPLACEMENT: "mm", ProductType.COHERENCE: "dimensionless", ProductType.LOS_VELOCITY: "mm/year"}
    stat_of = {
        ProductType.LOS_DISPLACEMENT: disp_stats.result("mm"),
        ProductType.COHERENCE: coh_acc.result(),
        ProductType.LOS_VELOCITY: vel_stats.result("mm/year"),
    }
    for kind, tmp in tmp_files.items():
        final = out_dirs[kind] / f"{kind.value.lower()}.tif"
        to_cog(tmp, final)
        if not cfg.keep_intermediates:
            tmp.unlink(missing_ok=True)
        result.outputs.append(OutputFile(
            kind=kind, path=str(final), units=unit_of[kind], nodata=None, width=grid.width, height=grid.height,
            crs=f"EPSG:{grid.epsg}" if grid.epsg else None, stats=stat_of[kind],
            extra={"bounds_4326": list(bounds), "polarization": pol,
                   "sign_convention": SIGN_CONVENTION if kind is not ProductType.COHERENCE else None},
        ))
    result.stats = {
        "displacement": stat_of[ProductType.LOS_DISPLACEMENT],
        "coherence": stat_of[ProductType.COHERENCE] if has_coh else None,
        "velocity": stat_of[ProductType.LOS_VELOCITY] if do_velocity else None,
        "masked_by_coherence_threshold": masked_by_coh,
        "masked_by_connected_components": masked_by_cc,
        "polarization": pol, "wavelength_m": lam, "temporal_baseline_days": baseline_days,
    }
    if stat_of[ProductType.LOS_DISPLACEMENT]["valid_pixels"] == 0:
        raise ProcessingError("no valid displacement pixels: every pixel was invalid or masked")
    return result


def software_versions() -> dict[str, str]:
    import rasterio

    return {
        "python": sys.version.split()[0], "numpy": np.__version__, "h5py": h5py.__version__,
        "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
        "external_tools": "none used",
    }


def now() -> datetime:
    return datetime.now(UTC)


def quality_report(
    *, rep: InspectionReport | None, cfg: ProcessingConfig, result: ProcessingResult | None, status: str,
    started: datetime, ended: datetime, input_ref: str, errors: list[str], extra_warnings: list[str] | None = None,
    file_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every run produces one, including failed/blocked runs. Units are explicit; labels never over-claim."""
    origin = rep.data_origin.value if rep else "UNKNOWN"
    synthetic = origin == "SYNTHETIC_FIXTURE"
    warnings = [*(result.warnings if result else (rep.warnings if rep else [])), *(extra_warnings or [])]
    return {
        "status": status,
        "input_ref": input_ref,
        "data_origin": origin,
        "label": "SYNTHETIC TEST DATA: not a satellite observation" if synthetic else (
            "Derived from a file registered as satellite data; NOT scientifically validated" if origin == "REAL_SATELLITE"
            else "Local file of unverified provenance; NOT scientifically validated"),
        "real_satellite_data": origin == "REAL_SATELLITE",
        "real_data_validation": "NOT_PERFORMED",
        "scientifically_validated": False,
        "file_integrity_validation": file_integrity or "not available (Phase 2 integrity checks are not scientific validation)",
        "measurement_kinds": {
            "raw_observation": "none (inputs are processed products)",
            "existing_processed_product_measurement": "unwrapped phase (rad), coherence (0-1) as delivered in the input",
            "newly_derived": "LOS displacement (mm), LOS velocity (mm/year) computed here",
        },
        "input": None if rep is None else {
            "file_name": rep.file_name, "file_size_bytes": rep.file_size_bytes, "product_type": rep.product_kind.value,
            "product_version": rep.product_version,
            "reference_time": rep.reference_time.isoformat() if rep.reference_time else None,
            "secondary_time": rep.secondary_time.isoformat() if rep.secondary_time else None,
            "orbit_direction": rep.orbit_direction, "wavelength_m": rep.wavelength_m,
            "perpendicular_baseline_m": rep.perpendicular_baseline_m,
            "crs": f"EPSG:{rep.grid.epsg}" if rep.grid and rep.grid.epsg else None,
            "resolution": [rep.grid.dx, rep.grid.dy] if rep.grid else None,
            "shape": [rep.grid.height, rep.grid.width] if rep.grid else None,
            "extent_4326": list(bounds_4326(rep.grid)) if rep.grid else None,
        },
        "statistics": result.stats if result else None,
        "software": software_versions(),
        "configuration": cfg.to_dict(),
        "sign_convention": SIGN_CONVENTION, "sign_convention_verified": SIGN_CONVENTION_VERIFIED,
        "limitations": [
            "LOS displacement is one component of 3D motion, relative to an unspecified reference.",
            "No atmospheric, ionospheric or tidal correction is applied here.",
            "Velocity is the mean over one interferogram's baseline, not a time series.",
            "A deformation raster is a measurement product, not a landslide risk map.",
        ],
        "warnings": warnings, "errors": errors,
        "started_at": started.isoformat(), "ended_at": ended.isoformat(),
    }
