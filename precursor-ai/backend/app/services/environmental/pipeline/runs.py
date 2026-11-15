"""Environmental pipeline: one run per monitored area, explicit stages, partial availability, retry without redoing work.

Principles (Phase 4):
* Inputs are Phase 2 `data_acquisitions` (NASADEM, GPM), user-placed files in data/external (soil, land cover) and
  DB tables (landslide catalog, earthquakes, Phase 3 deformation products). Nothing is downloaded here.
* A stage with no input ends NOT_AVAILABLE (recorded with a reason, never zero-filled); the run continues.
* A stage whose inputs and configuration are identical to an earlier PROCESSED layer is SKIPPED unless `force`.
* Every layer/feature carries origin, measurement kind and validation status NOT_VALIDATED.
* No prediction, score or ML anywhere in this module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import numpy as np
from geoalchemy2.shape import from_shape, to_shape
from pyproj import Transformer
from shapely.geometry import box
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import app.core.geo_env  # noqa: F401
from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models import (
    DataAcquisition, DeformationProduct, EarthquakeEvent, EnvironmentalFeature, EnvironmentalLayer,
    EnvironmentalProcessingRun, LandslideEvent, MonitoredArea,
)
from app.schemas.environmental import ProcessConfig
from app.services.environmental import queries, storage
from app.services.environmental.dem.dem_processor import compute_terrain, prepare_dem
from app.services.environmental.features.historical_event_features import historical_event_features
from app.services.environmental.features.insar_features import insar_features
from app.services.environmental.features.land_cover_features import land_cover_features
from app.services.environmental.features.rainfall_features import rainfall_features
from app.services.environmental.features.seismic_features import seismic_features
from app.services.environmental.features.soil_features import soil_features
from app.services.environmental.features.terrain_features import terrain_features
from app.services.environmental.land_cover.land_cover_processor import process_land_cover
from app.services.environmental.providers.land_cover import LandCoverProvider
from app.services.environmental.providers.soilgrids import SoilGridsProvider
from app.services.environmental.rainfall.half_hourly import HalfHourlyFile, process_rainfall_half_hourly
from app.services.environmental.rainfall.precipitation_processor import RainfallFile, process_rainfall
from app.services.environmental.raster.reference_grid import ReferenceGrid, align_layer_to_reference, build_reference_grid
from app.services.environmental.smap.smap_processor import SmapFile, process_smap
from app.services.environmental.features.smap_features import smap_features
from app.services.environmental import manifest as manifest_mod
from app.services.environmental.distances.distance_processor import process_distance
from app.services.environmental.external_inputs import discover_external
from app.services.environmental.features.distance_features import distance_features
from app.services.environmental.features.lithology_features import lithology_features
from app.services.environmental.features.vegetation_features import vegetation_features
from app.services.environmental.lithology.lithology_processor import process_lithology
from app.services.environmental.vegetation.ndvi_processor import process_ndvi
from app.services.environmental.raster.io import inspect_raster
from app.services.environmental.soil.soil_processor import process_soil
from app.services.environmental.types import (
    DataOrigin, EnvError, LayerKind, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance, RunStatus,
    StageName, StageStatus, ValidationStatus, RASTER_KINDS, TEMPORAL_OF,
)

log = logging.getLogger(__name__)
ALL_STAGES = [s.value for s in StageName]
READY = ("DOWNLOADED", "VALIDATED")  # Phase 2: a file is on disk
GOOD = ("PROCESSED", "PARTIALLY_PROCESSED")
TERMINAL_RUN = {RunStatus.COMPLETED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}
LIMITATIONS = [
    "Environmental measurements and summaries of source data are not landslide risk, probability or prediction.",
    "No dataset has been scientifically validated: file integrity and processing success are not validation.",
    "Resampling and AOI statistics never increase the native information resolution of a source.",
    "The NASA Global Landslide Catalog is a one-time export whose last event is dated 2017-09-28: incomplete, reporting-biased, not ground truth.",
    "Earthquakes are independent observations; no causal link to landslides is implied.",
]


def _now() -> datetime:
    return datetime.now(UTC)


def json_safe(o: Any) -> Any:
    """Recursively make values JSON/JSONB-safe: NaN/inf -> None, numpy -> python, datetime -> ISO, Path -> name."""
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [json_safe(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return json_safe(o.tolist())
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Path):
        return o.name
    if isinstance(o, uuid.UUID):
        return str(o)
    if hasattr(o, "value") and not isinstance(o, (str, int)):
        return o.value
    return o


def flatten_features(feat: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Feature dicts differ per group ({value, unit} items, plain lists, ...). Normalise to values / units / warnings."""
    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    src = feat.get("features")
    if isinstance(src, dict):
        for k, v in src.items():
            if isinstance(v, dict) and "value" in v:
                values[k] = v["value"]
                u = v.get("unit") or v.get("units")
                if u:
                    units[k] = str(u)
            else:
                values[k] = v
    elif "values" in feat:
        v = feat["values"]
        values["layers" if isinstance(v, list) else "classes"] = v
        if isinstance(feat.get("units"), str):
            units["classes"] = feat["units"]
    for k, v in feat.items():
        if k in ("features", "values", "warnings", "measurement_kind", "units") or k in values:
            continue
        values[k] = v
    return json_safe(values), units, [str(w) for w in feat.get("warnings", [])]


_FILE_PREFIX = re.compile(r"^([^\s:]+\.[A-Za-z0-9]{2,5}): (.*)$")


def collapse_warnings(warnings: list[str]) -> list[str]:
    """Per-file warnings that differ only by file name become one line with a count ("... (9 files)")."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for w in warnings:
        m = _FILE_PREFIX.match(w)
        key, name = (m.group(2), m.group(1)) if m else (w, "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        if name:
            groups[key].append(name)
    out = []
    for key in order:
        n = len(groups[key])
        out.append(key if n == 0 else (f"{groups[key][0]}: {key}" if n == 1 else f"{key} ({n} files)"))
    return out


def _hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(json_safe(parts), sort_keys=True, default=str).encode()).hexdigest()


def _file_sig(paths: list[Path]) -> list[tuple[str, int]]:
    return sorted((p.name, p.stat().st_size) for p in paths)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Outcome:
    status: StageStatus
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class Ctx:
    db: Session
    run: EnvironmentalProcessingRun
    area: MonitoredArea
    aoi: Any
    cfg: ProcessConfig
    settings: Settings
    cancelled: Callable[[], bool]
    payloads: dict[str, dict[str, Any]] = field(default_factory=dict)  # feature group -> payload
    layer_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    dem_path: Path | None = None
    skipped_any: bool = False
    ref: ReferenceGrid | None = None

    def grid(self) -> ReferenceGrid:
        """The common metric grid, built once per run from the AOI (or the user's CRS/resolution) and stored on the run."""
        if self.ref is None:
            self.ref = build_reference_grid(self.aoi, crs=self.cfg.grid_crs, resolution_m=self.cfg.grid_resolution_m)
            self.run.reference_grid = json_safe(self.ref.to_dict())
            self.db.commit()
        return self.ref

    @property
    def root(self) -> Path:
        return self.settings.data_root


class EnvironmentalRunService:
    def __init__(self, session_factory: Callable[[], Session], settings: Settings, *, executor: Executor | None = None):
        self.sf = session_factory
        self.settings = settings
        self._executor = executor

    @property
    def executor(self) -> Executor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(1, thread_name_prefix="env")
        return self._executor

    # ---- run lifecycle -------------------------------------------------------------------------
    def create_run(self, db: Session, area_id: uuid.UUID, cfg: ProcessConfig) -> EnvironmentalProcessingRun:
        if db.get(MonitoredArea, area_id) is None:
            raise NotFoundError(f"Monitored area {area_id} not found")
        stages = cfg.stages or ALL_STAGES
        bad = [s for s in stages if s not in ALL_STAGES]
        if bad:
            raise ValidationFailed(f"unknown stage(s): {', '.join(bad)}")
        active = db.scalar(select(func.count()).select_from(EnvironmentalProcessingRun).where(
            EnvironmentalProcessingRun.area_id == area_id,
            EnvironmentalProcessingRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value])))
        if active:
            raise ConflictError("a run is already queued or running for this area")
        run = EnvironmentalProcessingRun(area_id=area_id, status=RunStatus.QUEUED.value, stages=[],
                                         config=json_safe({**cfg.model_dump(), "stages": stages}), warnings=[])
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def submit(self, run_id: uuid.UUID) -> None:
        self.executor.submit(self.execute, run_id)

    def cancel(self, db: Session, run_id: uuid.UUID) -> EnvironmentalProcessingRun:
        run = db.get(EnvironmentalProcessingRun, run_id, populate_existing=True)
        if run is None:
            raise NotFoundError(f"Processing run {run_id} not found")
        if RunStatus(run.status) in TERMINAL_RUN:
            raise ConflictError(f"run already {run.status}")
        run.cancel_requested = True
        if run.status == RunStatus.QUEUED.value:
            run.status, run.completed_at = RunStatus.CANCELLED.value, _now()
        db.commit()
        return run

    def recover_stale_runs(self) -> int:
        with self.sf() as s:
            rows = list(s.scalars(select(EnvironmentalProcessingRun).where(
                EnvironmentalProcessingRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]))))
            for r in rows:
                r.status, r.error_message, r.completed_at = RunStatus.FAILED.value, "interrupted by a server restart; start a new run", _now()
            s.commit()
            return len(rows)

    def execute(self, run_id: uuid.UUID) -> None:
        s = self.sf()
        try:
            run = s.get(EnvironmentalProcessingRun, run_id, populate_existing=True)
            if run is None or RunStatus(run.status) in TERMINAL_RUN:
                return
            self._execute(s, run)
        except Exception:
            log.exception("environmental run %s crashed", run_id)
            s.rollback()
            run = s.get(EnvironmentalProcessingRun, run_id, populate_existing=True)
            if run is not None and RunStatus(run.status) not in TERMINAL_RUN:
                run.status, run.error_message, run.completed_at = RunStatus.FAILED.value, "unexpected internal error (see server log)", _now()
                s.commit()
        finally:
            s.close()

    # ---- the pipeline --------------------------------------------------------------------------
    def _stage_log(self, s: Session, run: EnvironmentalProcessingRun, name: str, status: str, message: str = "") -> None:
        stages = [dict(x) for x in run.stages]
        now = _now().isoformat()
        cur = next((x for x in stages if x["name"] == name), None)
        if cur is None:
            cur = {"name": name, "started_at": now}
            stages.append(cur)
        cur.update(status=status, message=message)
        if status != "RUNNING":
            cur["ended_at"] = now
        run.stages = stages
        run.current_stage = name if status == "RUNNING" else run.current_stage
        s.commit()

    def _execute(self, s: Session, run: EnvironmentalProcessingRun) -> None:
        area = s.get(MonitoredArea, run.area_id)
        if area is None:
            run.status, run.error_message, run.completed_at = RunStatus.FAILED.value, "monitored area no longer exists", _now()
            s.commit()
            return
        cfg = ProcessConfig(**{k: v for k, v in run.config.items() if k in ProcessConfig.model_fields})
        storage.ensure_layout(self.settings.data_root)
        ctx = Ctx(s, run, area, to_shape(area.geometry), cfg, self.settings,
                  cancelled=lambda: bool(s.refresh(run) or run.cancel_requested))
        run.status, run.started_at = RunStatus.RUNNING.value, _now()
        s.commit()
        wanted = [n for n in ALL_STAGES if n in (run.config.get("stages") or ALL_STAGES)]
        handlers: dict[str, Callable[[Ctx], Outcome]] = {
            "DEM": self._dem, "TERRAIN": self._terrain, "RAINFALL": self._rainfall, "SMAP": self._smap, "SOIL": self._soil,
            "LAND_COVER": self._land_cover, "LITHOLOGY": self._lithology, "NDVI": self._ndvi, "DISTANCES": self._distances,
            "HISTORICAL_LANDSLIDES": self._historical, "SEISMIC": self._seismic, "INSAR": self._insar,
            "REFERENCE_GRID": self._reference_grid, "FEATURES": self._features, "MANIFEST": self._manifest, "QUALITY": self._quality,
        }
        results: dict[str, Outcome] = {}
        run_warnings: list[str] = []
        for name in wanted:
            if ctx.cancelled():
                run.status, run.completed_at, run.error_message = RunStatus.CANCELLED.value, _now(), "cancelled by user"
                s.commit()
                return
            if name == "INSAR" and not cfg.include_insar:
                self._stage_log(s, run, name, StageStatus.SKIPPED.value, "include_insar=false")
                results[name] = Outcome(StageStatus.SKIPPED)
                continue
            self._stage_log(s, run, name, "RUNNING")
            try:
                out = handlers[name](ctx)
            except NotAvailable as exc:
                out = Outcome(StageStatus.NOT_AVAILABLE, str(exc))
                self._record_unavailable(ctx, name, str(exc))
            except (EnvError, ValueError, OSError) as exc:
                s.rollback()
                out = Outcome(StageStatus.FAILED, f"{type(exc).__name__}: {exc}")
                log.warning("stage %s failed for run %s: %s", name, run.id, exc)
            except Exception as exc:  # a bug in one stage must not hide the others' results
                s.rollback()
                log.exception("stage %s crashed", name)
                out = Outcome(StageStatus.FAILED, f"unexpected error ({type(exc).__name__}); see server log")
            results[name] = out
            run_warnings += [f"{name}: {w}" for w in out.warnings]
            self._stage_log(s, run, name, out.status.value, out.message)
        st = {k: v.status for k, v in results.items()}
        done = [k for k, v in st.items() if v in (StageStatus.DONE, StageStatus.SKIPPED, StageStatus.PARTIAL)]
        failed = [k for k, v in st.items() if v is StageStatus.FAILED]
        missing = [k for k, v in st.items() if v is StageStatus.NOT_AVAILABLE]
        if failed and not done:
            run.status = RunStatus.FAILED.value
        elif failed or missing or any(v is StageStatus.PARTIAL for v in st.values()):
            run.status = RunStatus.PARTIAL.value
        else:
            run.status = RunStatus.COMPLETED.value
        if failed:
            run.error_message = "stage(s) failed: " + ", ".join(failed)
        if missing:
            run_warnings.append("no source data available for: " + ", ".join(missing))
        run.warnings, run.completed_at, run.current_stage = run_warnings, _now(), None
        s.commit()

    # ---- helpers ---------------------------------------------------------------------------------
    def _acquisitions(self, ctx: Ctx, provider: str, *, global_ok: bool = False) -> list[DataAcquisition]:
        cond = func.ST_Intersects(DataAcquisition.spatial_footprint, ctx.area.geometry)
        if global_ok:
            cond = or_(cond, DataAcquisition.spatial_footprint.is_(None))
        q = select(DataAcquisition).where(
            DataAcquisition.provider == provider, DataAcquisition.local_file_path.is_not(None),
            DataAcquisition.status.in_(READY), cond).order_by(DataAcquisition.acquisition_start, DataAcquisition.granule_id)
        return list(ctx.db.scalars(q))

    def _acq_files(self, ctx: Ctx, acqs: list[DataAcquisition], warnings: list[str]) -> list[tuple[DataAcquisition, Path]]:
        out = []
        for a in acqs:
            try:
                out.append((a, storage.resolve_input_under(ctx.root, a.local_file_path or "", "raw")))
            except (FileNotFoundError, ValueError) as exc:
                warnings.append(f"{a.granule_id}: registered file unusable ({type(exc).__name__}); ignored")
        return out

    def _prior(self, ctx: Ctx, kind: LayerKind, h: str) -> EnvironmentalLayer | None:
        if ctx.cfg.force:
            return None
        lay = ctx.db.scalars(select(EnvironmentalLayer).where(
            EnvironmentalLayer.area_id == ctx.area.id, EnvironmentalLayer.layer_type == kind.value,
            EnvironmentalLayer.input_hash == h, EnvironmentalLayer.status.in_(GOOD))
            .order_by(EnvironmentalLayer.created_at.desc())).first()
        if lay is None:
            return None
        if lay.file_path:
            try:
                if not storage.resolve_output(ctx.root, lay.file_path).is_file():
                    return None
            except ValueError:
                return None
        return lay

    def _adopt(self, ctx: Ctx, group: str, lay: EnvironmentalLayer) -> Outcome:
        pl = (lay.statistics or {}).get("feature_payload")
        if pl:
            ctx.payloads[group] = pl
        ctx.layer_ids[lay.layer_type] = lay.id
        ctx.skipped_any = True
        return Outcome(StageStatus.SKIPPED, "identical inputs already processed; reused")

    def _footprint(self, bounds: tuple[float, float, float, float] | None, crs: str | None):
        if bounds is None:
            return None
        l, b, r, t = bounds
        if crs and crs.upper() not in ("EPSG:4326", "OGC:CRS84"):
            tr = Transformer.from_crs(crs, 4326, always_xy=True)
            pts = [tr.transform(x, y) for x in (l, r) for y in (b, t)]
            l, r = min(p[0] for p in pts), max(p[0] for p in pts)
            b, t = min(p[1] for p in pts), max(p[1] for p in pts)
        return from_shape(box(l, b, r, t), srid=4326)

    def _add_layer(self, ctx: Ctx, kind: LayerKind, prov: Provenance, quality: LayerQuality, status: LayerStatus, *,
                   path: Path | None = None, stats: dict[str, Any] | None = None, input_hash: str | None = None,
                   units: str | None = None, processing_resolution: dict | None = None, deformation_product_id=None,
                   bounds: tuple | None = None, crs: str | None = None, t0: datetime | None = None, t1: datetime | None = None,
                   payload: dict | None = None) -> EnvironmentalLayer:
        meta = inspect_raster(path) if path is not None else None
        fp_bounds = bounds or (tuple(meta.bounds) if meta else tuple(ctx.aoi.bounds))
        lay = EnvironmentalLayer(
            area_id=ctx.area.id, run_id=ctx.run.id, deformation_product_id=deformation_product_id, layer_type=kind.value,
            source_provider=prov.provider, dataset_name=prov.dataset_name, dataset_version=prov.dataset_version,
            measurement_kind=prov.measurement_kind.value, data_origin=prov.origin.value,
            validation_status=ValidationStatus.NOT_VALIDATED.value, status=status.value, input_hash=input_hash,
            temporal_kind=TEMPORAL_OF[kind].value,
            file_path=storage.to_relative(ctx.root, path) if path else None, file_format="GTiff" if path else None,
            file_size_bytes=path.stat().st_size if path else None, checksum_sha256=_sha256(path) if path else None,
            units=units or prov.units, crs=meta.crs if meta else crs, width=meta.width if meta else None,
            height=meta.height if meta else None, nodata=None if not meta or meta.nodata is None or (isinstance(meta.nodata, float) and math.isnan(meta.nodata)) else float(meta.nodata),
            native_resolution=json_safe(quality.native_resolution), processing_resolution=json_safe(processing_resolution or quality.processing_resolution),
            temporal_start=t0 or prov.observation_start, temporal_end=t1 or prov.observation_end,
            footprint=self._footprint(fp_bounds, meta.crs if meta else crs), provenance=json_safe(prov.to_dict()),
            quality=json_safe(quality.to_dict()), statistics=json_safe({**(stats or {}), **({"feature_payload": payload} if payload else {})}),
        )
        ctx.db.add(lay)
        ctx.db.commit()
        ctx.layer_ids[kind.value] = lay.id
        return lay

    def _record_unavailable(self, ctx: Ctx, name: str, reason: str) -> None:
        kinds = {"DEM": [LayerKind.ELEVATION], "TERRAIN": [LayerKind.SLOPE, LayerKind.ASPECT], "RAINFALL": [LayerKind.RAINFALL],
                 "SMAP": [LayerKind.SMAP_SOIL_MOISTURE], "SOIL": [LayerKind.SOIL], "LAND_COVER": [LayerKind.LAND_COVER],
                 "LITHOLOGY": [LayerKind.LITHOLOGY], "NDVI": [LayerKind.NDVI],
                 "DISTANCES": [LayerKind.DISTANCE_RIVER, LayerKind.DISTANCE_FAULT, LayerKind.DISTANCE_ROAD],
                 "HISTORICAL_LANDSLIDES": [LayerKind.HISTORICAL_LANDSLIDES], "SEISMIC": [LayerKind.SEISMIC],
                 "INSAR": [LayerKind.INSAR_DISPLACEMENT]}
        todo = kinds.get(name)
        if todo is None:
            return
        group = {"DEM": "terrain", "TERRAIN": "terrain", "RAINFALL": "rainfall", "SMAP": "smap", "SOIL": "soil", "LAND_COVER": "land_cover",
                 "LITHOLOGY": "lithology", "NDVI": "vegetation", "DISTANCES": "distances",
                 "HISTORICAL_LANDSLIDES": "historical_landslides", "SEISMIC": "seismic", "INSAR": "insar"}[name]
        for kind in todo:
            prov = Provenance(provider="NONE", dataset_name=kind.value, origin=DataOrigin.LOCAL_UNVERIFIED)
            self._add_layer(ctx, kind, prov, LayerQuality(warnings=[reason]), LayerStatus.NOT_AVAILABLE, stats={"reason": reason})
        if name != "TERRAIN" or "terrain" not in ctx.payloads:
            ctx.payloads.setdefault(group, {"status": "NOT_AVAILABLE", "values": {}, "units": {}, "warnings": [reason],
                                            "origin": "NONE", "kind": MeasurementKind.STATISTICAL_SUMMARY.value, "lineage": []})

    def _payload(self, feat: dict[str, Any], prov: Provenance, status: str, layer: EnvironmentalLayer | None, extra_lineage=None) -> dict[str, Any]:
        values, units, warnings = flatten_features(feat)
        return json_safe({"status": status, "values": values, "units": units, "warnings": warnings, "origin": prov.origin.value,
                          "kind": MeasurementKind.STATISTICAL_SUMMARY.value,
                          "lineage": [{"layer_id": str(layer.id) if layer else None, "provenance": prov.to_dict()}, *(extra_lineage or [])]})

    # ---- stages ------------------------------------------------------------------------------------
    def _dem(self, ctx: Ctx) -> Outcome:
        warnings: list[str] = []
        pairs = self._acq_files(ctx, self._acquisitions(ctx, "NASADEM"), warnings)
        if not pairs:
            raise NotAvailable("no downloaded NASADEM tile intersects this area (a Phase 2 download is required)")
        paths = [p for _, p in pairs]
        h = _hash("dem", _file_sig(paths), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.ELEVATION, h)
        if prior is not None:
            ctx.dem_path = storage.resolve_output(ctx.root, prior.file_path)
            out = self._adopt(ctx, "terrain", prior)
            return out
        res = prepare_dem(paths, ctx.aoi, storage.area_dir(ctx.root, ctx.area.id, "dem"))
        ctx.dem_path = res.elevation_path
        origin = DataOrigin.SYNTHETIC_FIXTURE if res.is_synthetic else DataOrigin.REAL_SATELLITE
        prov = Provenance(provider="NASADEM", dataset_name="NASADEM_HGT", dataset_version="001", origin=origin,
                          measurement_kind=MeasurementKind.SOURCE_OBSERVATION, acquisition_ids=[str(a.id) for a, _ in pairs],
                          source_files=[p.name for p in paths], units=res.units, method="mosaic + AOI clip", notes=res.warnings)
        self._add_layer(ctx, LayerKind.ELEVATION, prov, res.quality, LayerStatus.PROCESSED, path=res.elevation_path, input_hash=h,
                        stats={"tiles_used": res.tiles_used, "aoi_coverage_percent": res.aoi_coverage_percent})
        return Outcome(StageStatus.DONE if res.aoi_coverage_percent >= 99.9 else StageStatus.PARTIAL,
                       f"{len(paths)} tile(s); AOI covered {res.aoi_coverage_percent:.1f}%", res.warnings + warnings)

    def _terrain(self, ctx: Ctx) -> Outcome:
        if ctx.dem_path is None:  # DEM stage not run in this request: reuse the newest elevation layer
            lay = next((x for x in ctx.db.scalars(select(EnvironmentalLayer).where(
                EnvironmentalLayer.area_id == ctx.area.id, EnvironmentalLayer.layer_type == "ELEVATION",
                EnvironmentalLayer.status.in_(GOOD)).order_by(EnvironmentalLayer.created_at.desc())) if x.file_path), None)
            if lay is None:
                raise NotAvailable("no elevation layer: run the DEM stage first (needs downloaded NASADEM tiles)")
            ctx.dem_path = storage.resolve_output(ctx.root, lay.file_path)
        dem_layer = ctx.db.scalars(select(EnvironmentalLayer).where(
            EnvironmentalLayer.area_id == ctx.area.id, EnvironmentalLayer.layer_type == "ELEVATION",
            EnvironmentalLayer.status.in_(GOOD)).order_by(EnvironmentalLayer.created_at.desc())).first()
        h = _hash("terrain", dem_layer.checksum_sha256 if dem_layer else None)
        prior = self._prior(ctx, LayerKind.SLOPE, h)
        if prior is not None:
            return self._adopt(ctx, "terrain", prior)
        out_dir = storage.area_dir(ctx.root, ctx.area.id, "dem")
        ter = compute_terrain(ctx.dem_path, out_dir)
        origin = DataOrigin(dem_layer.data_origin) if dem_layer else DataOrigin.LOCAL_UNVERIFIED
        base = dict(origin=origin, acquisition_ids=(dem_layer.provenance or {}).get("acquisition_ids", []) if dem_layer else [],
                    source_files=["elevation.tif"], measurement_kind=MeasurementKind.DERIVED_MEASUREMENT)
        feat = terrain_features(ctx.dem_path, ter.slope_path, ter.aspect_path, ctx.aoi)
        sp = Provenance(provider="NASADEM", dataset_name="slope (Horn, derived)", units="degree", method="Horn 3x3; geographic cell sizes in metres", **base)
        ap = Provenance(provider="NASADEM", dataset_name="aspect (downslope azimuth, derived)", units="degree",
                        method="clockwise from north; flat cells are no-data", **base)
        slope_layer = self._add_layer(ctx, LayerKind.SLOPE, sp, ter.slope_quality, LayerStatus.PROCESSED, path=ter.slope_path, input_hash=h,
                                      stats={"flat_pixels": ter.flat_count})
        self._add_layer(ctx, LayerKind.ASPECT, ap, ter.aspect_quality, LayerStatus.PROCESSED, path=ter.aspect_path, input_hash=h)
        ctx.payloads["terrain"] = self._payload(feat, sp, "PROCESSED", slope_layer,
                                                [{"layer_id": str(dem_layer.id) if dem_layer else None}])
        slope_layer.statistics = json_safe({**(slope_layer.statistics or {}), "feature_payload": ctx.payloads["terrain"]})
        ctx.db.commit()
        return Outcome(StageStatus.DONE, "slope and aspect derived", ter.warnings)

    def _rainfall(self, ctx: Ctx) -> Outcome:
        warnings: list[str] = []
        hh = ctx.cfg.rainfall_resolution == "half_hourly"
        pairs = self._acq_files(ctx, self._acquisitions(ctx, "GPM", global_ok=True), warnings)
        # Phase 2 stores daily and half-hourly IMERG under one provider; the collection short name tells them apart.
        pairs = [(a, p) for a, p in pairs if a.acquisition_start is not None
                 and (("IMERGHH" in ((a.collection.collection_short_name if a.collection else "") or "").upper()) == hh)]
        if not pairs:
            raise NotAvailable(f"no downloaded GPM IMERG {'half-hourly' if hh else 'daily'} file for this area (a Phase 2 download is required)")
        days = [a.acquisition_start.date() for a, _ in pairs]
        start, end = ctx.cfg.start_date or min(days), ctx.cfg.end_date or max(days)
        sel = [(a, p) for a, p in pairs if start <= a.acquisition_start.date() <= end]
        if not sel:
            raise NotAvailable(f"no GPM file inside {start}..{end}")
        files = ([HalfHourlyFile(a.acquisition_start, p, str(a.id)) for a, p in sel] if hh
                 else [RainfallFile(a.acquisition_start.date(), p, str(a.id)) for a, p in sel])
        windows = tuple(ctx.cfg.rolling_windows)
        h = _hash("rain", "half_hourly" if hh else "daily", _file_sig([Path(f.path) for f in files]), str(start), str(end), windows, ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.RAINFALL, h)
        if prior is not None:
            return self._adopt(ctx, "rainfall", prior)
        res = (process_rainfall_half_hourly(files, ctx.aoi, start, end, windows) if hh
               else process_rainfall(files, ctx.aoi, start, end, windows))
        daily = [{"date": d["date"], "precipitation_mm": d["precip_mm_day"], "observed": d["observed"]} for d in res.daily]
        monthly = [{"date": m["month"], "precipitation_mm": m["sum_mm"], "observed": bool(m["complete"])} for m in res.monthly]
        rolling = {f"{w}d": [{"date": r["date"], "precipitation_mm": r.get(f"sum_{w}d_mm"), "observed": r.get(f"sum_{w}d_mm") is not None}
                             for r in res.rolling] for w in res.windows}
        status = LayerStatus.PROCESSED if res.status.value == "PROCESSED" else LayerStatus.PARTIALLY_PROCESSED
        prov = res.provenance_accumulations
        feat = rainfall_features(res)
        lay = self._add_layer(
            ctx, LayerKind.RAINFALL, prov, res.quality, status, input_hash=h, units="mm",
            t0=datetime.combine(start, time.min, UTC), t1=datetime.combine(end, time.min, UTC),
            stats={"daily": daily, "monthly": monthly, "rolling": rolling, "observed_days": res.counts["observed_days"],
                   "missing_days": res.counts["missing_days"], "notes": collapse_warnings(res.warnings), "counts": res.counts, "file_errors": res.file_errors})
        pl = self._payload(feat, prov, status.value, lay)
        ctx.payloads["rainfall"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE if status is LayerStatus.PROCESSED else StageStatus.PARTIAL,
                       f"{res.counts['observed_days']} observed / {res.counts['missing_days']} missing days", collapse_warnings(res.warnings))

    def _external(self, ctx: Ctx, provider) -> list[Path]:
        return provider.local_inputs(ctx.root, ctx.aoi)

    def _soil(self, ctx: Ctx) -> Outcome:
        files = self._external(ctx, SoilGridsProvider())
        if not files:
            raise NotAvailable("no SoilGrids GeoTIFF placed in data/external/soilgrids covers this area (download needs approval)")
        h = _hash("soil", _file_sig(files), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.SOIL, h)
        if prior is not None:
            return self._adopt(ctx, "soil", prior)
        res = process_soil(files, ctx.aoi, out_dir=storage.area_dir(ctx.root, ctx.area.id, "soil"))
        feat = soil_features(res)
        status = LayerStatus.PROCESSED
        first = None
        for ent in (res.rasters or [None]):
            prov = res.provenance
            if ent is not None:
                prov = Provenance(**{**res.provenance.__dict__, "dataset_name": f"SoilGrids {ent['property']} {ent['top_cm']}-{ent['bottom_cm']}cm {ent['statistic']}",
                                     "units": ent.get("units") or res.provenance.units})
            lay = self._add_layer(ctx, LayerKind.SOIL, prov, res.quality, status, input_hash=h, stats={"layers": res.layers},
                                  path=Path(ent["path"]) if ent else None, units=(ent or {}).get("units"))
            pl = self._payload(feat, res.provenance, status.value, lay)
            lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
            first = first or pl
        ctx.payloads["soil"] = first
        ctx.db.commit()
        return Outcome(StageStatus.DONE, f"{len(res.layers)} property/depth layer(s)", res.warnings)

    def _land_cover(self, ctx: Ctx) -> Outcome:
        files = self._external(ctx, LandCoverProvider())
        if not files:
            raise NotAvailable("no land-cover GeoTIFF placed in data/external/land_cover covers this area (download needs approval)")
        h = _hash("lc", _file_sig(files), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.LAND_COVER, h)
        if prior is not None:
            return self._adopt(ctx, "land_cover", prior)
        res = process_land_cover(files, ctx.aoi, out_dir=storage.area_dir(ctx.root, ctx.area.id, "land_cover"))
        feat = land_cover_features(res)
        stats = {"classes": res.classes, "unknown_classes": res.unknown_classes, "year": res.year, "version": res.version,
                 "legend": [{"id": c["class_id"], "name": c["name"], "color": c["color"]} for c in res.classes]}
        first = None
        for ent in (res.rasters or [None]):
            prov = res.provenance
            if ent is not None and len(res.rasters) > 1:
                prov = Provenance(**{**res.provenance.__dict__, "dataset_name": f"{res.provenance.dataset_name} {ent.get('name', '')}".strip()})
            lay = self._add_layer(ctx, LayerKind.LAND_COVER, prov, res.quality, LayerStatus.PROCESSED, input_hash=h, stats=stats,
                                  path=Path(ent["path"]) if ent else None)
            pl = self._payload(feat, res.provenance, "PROCESSED", lay)
            lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
            first = first or pl
        ctx.payloads["land_cover"] = first
        ctx.db.commit()
        return Outcome(StageStatus.DONE, f"{len(res.classes)} class(es), year {res.year}", res.warnings)

    def _smap(self, ctx: Ctx) -> Outcome:
        warnings: list[str] = []
        pairs = [(a, p) for a, p in self._acq_files(ctx, self._acquisitions(ctx, "SMAP", global_ok=True), warnings) if a.acquisition_start is not None]
        if not pairs:
            raise NotAvailable("no downloaded SMAP file for this area (optional dataset; a Phase 2 download with ENABLE_SMAP is required)")
        days = [a.acquisition_start.date() for a, _ in pairs]
        start, end = ctx.cfg.start_date or min(days), ctx.cfg.end_date or max(days)
        sel = [(a, p) for a, p in pairs if start <= a.acquisition_start.date() <= end]
        if not sel:
            raise NotAvailable(f"no SMAP file inside {start}..{end}")
        files = [SmapFile(a.acquisition_start.date(), p, str(a.id)) for a, p in sel]
        h = _hash("smap", _file_sig([f.path for f in files]), str(start), str(end), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.SMAP_SOIL_MOISTURE, h)
        if prior is not None:
            return self._adopt(ctx, "smap", prior)
        res = process_smap(files, ctx.aoi, start, end)
        status = LayerStatus.PROCESSED if res.status.value == "PROCESSED" else LayerStatus.PARTIALLY_PROCESSED
        feat = smap_features(res)
        lay = self._add_layer(ctx, LayerKind.SMAP_SOIL_MOISTURE, res.provenance, res.quality, status, input_hash=h, units="cm3/cm3",
                              t0=datetime.combine(start, time.min, UTC), t1=datetime.combine(end, time.min, UTC),
                              stats={"daily": res.daily, "counts": res.counts, "notes": collapse_warnings(res.warnings),
                                     "file_errors": res.file_errors, "quality_filter": res.quality_filter})
        pl = self._payload(feat, res.provenance, status.value, lay)
        ctx.payloads["smap"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE if status is LayerStatus.PROCESSED else StageStatus.PARTIAL,
                       f"{res.counts.get('observed_days')} observed / {res.counts.get('missing_days')} missing days", collapse_warnings(res.warnings))

    def _on_grid(self, ctx: Ctx, lay: EnvironmentalLayer, res_path: Path) -> None:
        """Layers written directly on the reference grid by their own stage are their own aligned copy."""
        lay.aligned_file_path = storage.to_relative(ctx.root, res_path)
        lay.statistics = json_safe({**(lay.statistics or {}), "aligned_grid_hash": _hash(ctx.grid().to_dict())})

    def _lithology(self, ctx: Ctx) -> Outcome:
        files = discover_external(ctx.root, "lithology", ctx.aoi, (".tif", ".tiff", ".geojson", ".json"))
        if not files:
            raise NotAvailable("no lithology/geology file in data/external/lithology covers this area (user-provided; nothing is downloaded)")
        rg = ctx.grid()
        h = _hash("lith", _file_sig(files), rg.to_dict(), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.LITHOLOGY, h)
        if prior is not None:
            return self._adopt(ctx, "lithology", prior)
        res = process_lithology(files, ctx.aoi, rg.grid, storage.area_dir(ctx.root, ctx.area.id, "aligned"))
        feat = lithology_features(res)
        lay = self._add_layer(ctx, LayerKind.LITHOLOGY, res.provenance, res.quality, res.status, path=res.path, input_hash=h,
                              stats={**res.stats, "classes": res.classes, "unknown_classes": res.unknown_classes,
                                     "legend": [{"id": c["class_id"], "name": c["name"], "color": c.get("color") or "#888888"} for c in res.classes]})
        self._on_grid(ctx, lay, res.path)
        pl = self._payload(feat, res.provenance, res.status.value, lay)
        ctx.payloads["lithology"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE if res.status is LayerStatus.PROCESSED else StageStatus.PARTIAL,
                       f"{len(res.classes)} class(es) on the reference grid", res.warnings)

    def _ndvi(self, ctx: Ctx) -> Outcome:
        files = discover_external(ctx.root, "ndvi", ctx.aoi, (".tif", ".tiff"))
        if not files:
            raise NotAvailable("no NDVI raster in data/external/ndvi covers this area (user-provided; nothing is downloaded)")
        rg = ctx.grid()
        h = _hash("ndvi", _file_sig(files), rg.to_dict(), ctx.aoi.wkt)
        prior = self._prior(ctx, LayerKind.NDVI, h)
        if prior is not None:
            return self._adopt(ctx, "vegetation", prior)
        res = process_ndvi(files, ctx.aoi, rg.grid, storage.area_dir(ctx.root, ctx.area.id, "aligned"))
        feat = vegetation_features(res)
        lay = self._add_layer(ctx, LayerKind.NDVI, res.provenance, res.quality, res.status, path=res.path, input_hash=h,
                              units="NDVI (dimensionless)", stats={**res.stats, "observation": res.observation})
        self._on_grid(ctx, lay, res.path)
        pl = self._payload(feat, res.provenance, res.status.value, lay)
        ctx.payloads["vegetation"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE if res.status is LayerStatus.PROCESSED else StageStatus.PARTIAL,
                       "NDVI raster on the reference grid", res.warnings)

    _DIST_KINDS = (("river", "rivers", LayerKind.DISTANCE_RIVER), ("fault", "faults", LayerKind.DISTANCE_FAULT),
                   ("road", "roads", LayerKind.DISTANCE_ROAD))

    def _distances(self, ctx: Ctx) -> Outcome:
        found = []
        for kind, sub, lk in self._DIST_KINDS:
            # vector_buffer_deg: the nearest feature may lie just outside the AOI and must still be found
            files = discover_external(ctx.root, sub, ctx.aoi, (".geojson", ".json"), vector_buffer_deg=1.0)
            if files:
                found.append((kind, lk, files))
        if not found:
            raise NotAvailable("no river/fault/road GeoJSON in data/external/{rivers,faults,roads} (user-provided; nothing is downloaded)")
        rg = ctx.grid()
        hashes = {lk: _hash("dist", kind, _file_sig(files), rg.to_dict(), ctx.aoi.wkt) for kind, lk, files in found}
        priors = {lk: self._prior(ctx, lk, h) for lk, h in hashes.items()}
        missing = [lk for _, lk, _ in found if lk not in priors or priors[lk] is None]
        absent = [lk for _, _, lk in self._DIST_KINDS if lk not in hashes]
        for lk in absent:  # kinds without input are reported, never filled
            prov = Provenance(provider="NONE", dataset_name=lk.value, origin=DataOrigin.LOCAL_UNVERIFIED)
            self._add_layer(ctx, lk, prov, LayerQuality(warnings=["no input vectors"]), LayerStatus.NOT_AVAILABLE,
                            stats={"reason": f"no {lk.value.split('_')[1].lower()} vectors placed in data/external"})
        if not missing:
            first = next(iter(priors.values()))
            out = self._adopt(ctx, "distances", first)
            return Outcome(out.status, out.message + (f"; no input for {', '.join(a.value for a in absent)}" if absent else ""))
        results = []
        for kind, lk, files in found:
            results.append((lk, process_distance(kind, files, ctx.aoi, rg.grid, storage.area_dir(ctx.root, ctx.area.id, "aligned")), hashes[lk]))
        feat = distance_features([r for _, r, _ in results])
        warns: list[str] = []
        for lk, res, h in results:
            lay = self._add_layer(ctx, lk, res.provenance, res.quality, res.status, path=res.path, input_hash=h, units="metre", stats=dict(res.stats))
            self._on_grid(ctx, lay, res.path)
            pl = self._payload(feat, res.provenance, res.status.value, lay)
            ctx.payloads["distances"] = pl
            lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
            warns += res.warnings
        ctx.db.commit()
        part = bool(absent) or any(r.status is not LayerStatus.PROCESSED for _, r, _ in results)
        return Outcome(StageStatus.PARTIAL if part else StageStatus.DONE,
                       f"{len(results)} distance raster(s) in metres" + (f"; no input for {', '.join(a.value for a in absent)}" if absent else ""), warns)

    def _reference_grid(self, ctx: Ctx) -> Outcome:
        """Build the common grid and align every raster layer of the area to it (native files are kept)."""
        rg = ctx.grid()
        ghash = _hash(rg.to_dict())
        aligned_dir = storage.area_dir(ctx.root, ctx.area.id, "aligned")
        ok, failed, done, warns = 0, [], 0, list(rg.warnings)
        for lay in queries.latest_layers(ctx.db, ctx.area.id):
            kind = LayerKind(lay.layer_type)
            if kind not in RASTER_KINDS or lay.layer_type.startswith("INSAR") or lay.status not in GOOD or not lay.file_path:
                continue
            if (lay.statistics or {}).get("aligned_grid_hash") == ghash and lay.aligned_file_path:
                ok += 1
                continue
            try:
                src = storage.resolve_output(ctx.root, lay.file_path)
                if src.parent == aligned_dir:  # produced directly on the reference grid by its own stage
                    lay.aligned_file_path = lay.file_path
                    q = lay.quality or {}
                else:
                    slug = f"{lay.layer_type.lower()}_{hashlib.sha1(lay.dataset_name.encode()).hexdigest()[:8]}.tif"
                    al = align_layer_to_reference(src, rg, kind, aligned_dir / slug, aoi_wgs84=ctx.aoi)
                    lay.aligned_file_path = storage.to_relative(ctx.root, al.path)
                    q = {**(lay.quality or {}), "processing_resolution": rg.to_dict()["resolution"], "reference_grid_crs": rg.to_dict()["crs"],
                         "alignment_valid_percent": al.quality.valid_percent, "alignment_resampling": al.resampling,
                         "warnings": list((lay.quality or {}).get("warnings", [])) + [w for w in al.quality.warnings if w not in (lay.quality or {}).get("warnings", [])]}
                    lay.quality = json_safe(q)
                    lay.processing_resolution = json_safe(rg.to_dict()["resolution"])
                lay.statistics = json_safe({**(lay.statistics or {}), "aligned_grid_hash": ghash})
                done += 1
                ok += 1
            except (EnvError, NotAvailable, ValueError, OSError) as exc:
                failed.append(f"{lay.layer_type}: {exc}")
        ctx.db.commit()
        warns += [f"alignment failed for {f}" for f in failed]
        msg = f"grid {rg.to_dict()['crs']} @ {rg.resolution_m:g} m ({rg.grid.width}x{rg.grid.height}); {ok} raster layer(s) on the grid ({done} newly aligned)"
        return Outcome(StageStatus.PARTIAL if failed else StageStatus.DONE, msg, warns)

    def _manifest(self, ctx: Ctx) -> Outcome:
        m = manifest_mod.build_manifest(ctx.db, ctx.area.id)
        p = manifest_mod.write_manifest(ctx.root, ctx.area.id, m)
        c = m["counts"]
        return Outcome(StageStatus.DONE, f"manifest written ({p.name}): {c['available']} available / {c['not_available']} not available of {c['entries']} datasets")

    def _centroid(self, ctx: Ctx) -> tuple[float, float]:
        c = ctx.aoi.centroid
        return (c.x, c.y)

    def _historical(self, ctx: Ctx) -> Outcome:
        if not ctx.db.scalar(select(func.count()).select_from(LandslideEvent)):
            raise NotAvailable("the NASA Global Landslide Catalog has not been imported (Phase 2 importer); this is not 'zero events'")
        rows = ctx.db.scalars(select(LandslideEvent).where(func.ST_Intersects(LandslideEvent.geometry, ctx.area.geometry))).all()
        events = []
        for r in rows:
            p = to_shape(r.geometry)
            events.append({"id": r.external_event_id, "event_date": r.event_date, "lon": p.x, "lat": p.y,
                           "location_name": r.location_name, "country": r.country, "trigger": r.trigger})
        feat = historical_event_features(events, ctx.aoi, self._centroid(ctx))
        prov = Provenance(provider="NASA_GLC", dataset_name="NASA Global Landslide Catalog", dataset_version=(rows[0].dataset_version if rows else None),
                          origin=DataOrigin.REAL_SATELLITE if rows else DataOrigin.LOCAL_UNVERIFIED,
                          measurement_kind=MeasurementKind.SOURCE_OBSERVATION, method="spatial intersection with the AOI polygon",
                          notes=["one-time export whose last event is dated 2017-09-28; incomplete and reporting-biased"])
        # catalog rows are reference records, not satellite measurements: label them unverified rather than REAL_SATELLITE
        prov.origin = DataOrigin.LOCAL_UNVERIFIED
        q = LayerQuality(total_pixels=None, warnings=["cataloged events only; not a complete inventory"])
        lay = self._add_layer(ctx, LayerKind.HISTORICAL_LANDSLIDES, prov, q, LayerStatus.PROCESSED, stats={"count": len(events)})
        pl = self._payload(feat, prov, "PROCESSED", lay)
        ctx.payloads["historical_landslides"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE, f"{len(events)} cataloged event(s) in the AOI")

    def _seismic(self, ctx: Ctx) -> Outcome:
        if not ctx.db.scalar(select(func.count()).select_from(EarthquakeEvent)):
            raise NotAvailable("no earthquake records stored: use the seismic refresh (explicit user action) first")
        q = select(EarthquakeEvent).where(func.ST_Intersects(EarthquakeEvent.geometry, ctx.area.geometry))
        t0 = datetime.combine(ctx.cfg.start_date, time.min, UTC) if ctx.cfg.start_date else None
        t1 = datetime.combine(ctx.cfg.end_date, time.max, UTC) if ctx.cfg.end_date else None
        if t0:
            q = q.where(EarthquakeEvent.event_time >= t0)
        if t1:
            q = q.where(EarthquakeEvent.event_time <= t1)
        events = []
        for r in ctx.db.scalars(q).all():
            p = to_shape(r.geometry)
            events.append({"id": r.external_id, "time": r.event_time, "magnitude": r.magnitude, "depth_km": r.depth_km,
                           "place": r.place, "lon": p.x, "lat": p.y})
        feat = seismic_features(events, self._centroid(ctx), t0, t1)
        prov = Provenance(provider="USGS", dataset_name="USGS Earthquake Catalog", origin=DataOrigin.LOCAL_UNVERIFIED,
                          measurement_kind=MeasurementKind.SOURCE_OBSERVATION, method="spatial intersection with the AOI polygon",
                          observation_start=t0, observation_end=t1, notes=["independent observations; no causal link to landslides implied"])
        lay = self._add_layer(ctx, LayerKind.SEISMIC, prov, LayerQuality(), LayerStatus.PROCESSED, stats={"count": len(events)}, t0=t0, t1=t1)
        pl = self._payload(feat, prov, "PROCESSED", lay)
        ctx.payloads["seismic"] = pl
        lay.statistics = json_safe({**lay.statistics, "feature_payload": pl})
        ctx.db.commit()
        return Outcome(StageStatus.DONE, f"{len(events)} earthquake record(s) in the AOI/window")

    def _insar(self, ctx: Ctx) -> Outcome:
        prods = ctx.db.scalars(select(DeformationProduct).where(
            func.ST_Intersects(DeformationProduct.footprint, ctx.area.geometry))).all()
        if not prods:
            raise NotAvailable("no Phase 3 deformation product intersects this area")
        kind_map = {"LOS_DISPLACEMENT": LayerKind.INSAR_DISPLACEMENT, "COHERENCE": LayerKind.INSAR_COHERENCE, "LOS_VELOCITY": LayerKind.INSAR_VELOCITY}
        plain = []
        for p in prods:
            plain.append({"id": p.id, "product_type": p.product_type, "data_origin": p.data_origin, "units": p.units,
                          "statistics": p.statistics, "reference_time": p.reference_time, "secondary_time": p.secondary_time,
                          "scientifically_validated": p.scientifically_validated})
            prov = Provenance(provider="INSAR_PHASE3", dataset_name=f"Phase 3 {p.product_type}", origin=DataOrigin(p.data_origin),
                              measurement_kind=MeasurementKind.DERIVED_MEASUREMENT, units=p.units, insar_run_id=str(p.run_id),
                              observation_start=p.reference_time, observation_end=p.secondary_time,
                              method="referenced, not reprocessed", notes=["REFERENCE to a Phase 3 product; real-data validation NOT_PERFORMED",
                                                                           "a deformation map, not a risk map"])
            self._add_layer(ctx, kind_map[p.product_type], prov, LayerQuality(warnings=["Phase 3 product: sign convention unverified"]),
                            LayerStatus.PROCESSED, deformation_product_id=p.id, units=p.units, crs=p.crs,
                            stats=dict(p.statistics or {}), t0=p.reference_time, t1=p.secondary_time)
        feat = insar_features(plain)
        status = feat["status"]
        origins = {x["data_origin"] for x in plain}
        origin = DataOrigin.REAL_SATELLITE if status == "PROCESSED" else (DataOrigin.SYNTHETIC_FIXTURE if origins == {"SYNTHETIC_FIXTURE"} else DataOrigin.LOCAL_UNVERIFIED)
        values = {"products": feat["values"].get("products", []) if feat["values"] else [], "excluded": feat["excluded"]}
        ctx.payloads["insar"] = json_safe({
            "status": status, "values": values, "units": feat["units"], "warnings": feat["warnings"], "origin": origin.value,
            "kind": MeasurementKind.STATISTICAL_SUMMARY.value, "lineage": [{"deformation_product_id": str(x["id"]), "data_origin": x["data_origin"]} for x in plain]})
        msg = f"{len(plain)} product(s) referenced; {len(feat['included'])} eligible (real) / {len(feat['excluded'])} excluded"
        return Outcome(StageStatus.DONE if status == "PROCESSED" else StageStatus.PARTIAL, msg)

    def _features(self, ctx: Ctx) -> Outcome:
        n = 0
        for group, pl in ctx.payloads.items():
            row = ctx.db.scalars(select(EnvironmentalFeature).where(
                EnvironmentalFeature.run_id == ctx.run.id, EnvironmentalFeature.feature_group == group)).first()
            data = dict(values=pl.get("values", {}), units=pl.get("units", {}), lineage=pl.get("lineage", []),
                        measurement_kind=pl.get("kind", MeasurementKind.STATISTICAL_SUMMARY.value), data_origin=pl.get("origin", "NONE"),
                        status=pl.get("status", "NOT_AVAILABLE"), warnings=pl.get("warnings", []))
            if row is None:
                ctx.db.add(EnvironmentalFeature(run_id=ctx.run.id, area_id=ctx.area.id, feature_group=group, **data))
            else:
                for k, v in data.items():
                    setattr(row, k, v)
            n += 1
        ctx.db.commit()
        return Outcome(StageStatus.DONE, f"{n} feature group(s) recorded (descriptive summaries only)")

    def _quality(self, ctx: Ctx) -> Outcome:
        layers = list(ctx.db.scalars(select(EnvironmentalLayer).where(EnvironmentalLayer.area_id == ctx.area.id)
                                     .order_by(EnvironmentalLayer.created_at.desc())))
        latest: dict[str, EnvironmentalLayer] = {}
        for lay in layers:
            latest.setdefault(f"{lay.layer_type}|{lay.dataset_name}", lay)
        passed, failed, warns, per_layer = [], [], [], []
        for kind, lay in latest.items():
            q = lay.quality or {}
            passed += [f"{lay.layer_type}: {c}" for c in q.get("checks_passed", [])]
            failed += [f"{lay.layer_type}: {c}" for c in q.get("checks_failed", [])]
            warns += [f"{lay.layer_type}: {w}" for w in q.get("warnings", [])]
            per_layer.append({"layer_type": lay.layer_type, "dataset_name": lay.dataset_name, "temporal_kind": lay.temporal_kind, "on_reference_grid": bool(lay.aligned_file_path), "layer_id": str(lay.id), "status": lay.status, "data_origin": lay.data_origin,
                              "validation_status": lay.validation_status, "valid_percent": q.get("valid_percent"),
                              "missing_percent": q.get("missing_percent"), "aoi_coverage_percent": q.get("aoi_coverage_percent"),
                              "crs": lay.crs, "native_resolution": lay.native_resolution, "processing_resolution": lay.processing_resolution,
                              "temporal_start": lay.temporal_start, "temporal_end": lay.temporal_end})
        stages = list(ctx.run.stages)
        report = json_safe({
            "area_id": str(ctx.area.id), "run_id": str(ctx.run.id), "generated_at": _now(),
            "layers": per_layer, "stages": stages,
            "missing_datasets": [x["layer_type"] for x in per_layer if x["status"] not in GOOD],
            "passed_checks": passed, "failed_checks": failed, "warnings": warns,
            "contains_synthetic_data": any(x["data_origin"] == "SYNTHETIC_FIXTURE" for x in per_layer),
            "validation_status": "NOT_VALIDATED", "real_data_validation": "NOT_PERFORMED",
            "scientifically_validated": False,
            "skipped_identical_inputs": ctx.skipped_any, "limitations": LIMITATIONS,
            "spatial_limitations": ["Soil and land-cover statistics are computed on the AOI polygon at native resolution; no map raster is produced for them yet."],
            "temporal_limitations": ["Rainfall sums are reported only for fully observed months/windows; missing days are never zero-filled."],
        })
        ctx.run.quality_report = report
        try:
            d = storage.area_dir(ctx.root, ctx.area.id, "reports")
            (d / f"quality_report_{ctx.run.id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError:
            log.warning("could not write quality report file for %s", ctx.run.id)
        ctx.db.commit()
        return Outcome(StageStatus.DONE, "quality report generated")
