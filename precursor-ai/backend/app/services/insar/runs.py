"""Processing-run service: input selection, duplicate control, staged execution, status, provenance.

Reuses Phase 2: inputs are existing `data_acquisitions` rows (a file under data/raw). It never downloads,
never needs credentials and never modifies an input file.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models import DataAcquisition, DeformationProduct, InSARProcessingRun
from app.services.insar import storage
from app.services.insar.inspection import detect_kind, inspect_product
from app.services.insar.outputs import write_json
from app.services.insar.processing import Cancelled, process_gunw, quality_report
from app.services.insar.types import (
    TERMINAL, BlockedMissingInput, DataOrigin, InspectionReport, ProcessingConfig, ProcessingError,
    ProductKind, ProductType, RunStatus as S,
)

log = logging.getLogger(__name__)
PROCESSABLE = ("GUNW", "GSLC", "GCOV")
READY_STATUSES = ("DOWNLOADED", "VALIDATED")  # a file is on disk (Phase 2 states)
_ACTIVE = {S.PENDING, S.QUEUED, S.INSPECTING, S.PREPROCESSING, S.INTERFEROGRAM_GENERATION, S.PHASE_UNWRAPPING,
           S.DISPLACEMENT_CALCULATION, S.QUALITY_CHECK}


def _now() -> datetime:
    return datetime.now(UTC)


def config_hash(input_ref: str, cfg: ProcessingConfig) -> str:
    return hashlib.sha256(json.dumps({"in": input_ref, "cfg": cfg.to_dict()}, sort_keys=True).encode()).hexdigest()


class InSARRunService:
    def __init__(self, session_factory: Callable[[], Session], settings: Settings, *, executor: Executor | None = None):
        self.sf = session_factory
        self.settings = settings
        self._executor = executor

    @property
    def executor(self) -> Executor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(1, thread_name_prefix="insar")  # SAR jobs are memory heavy
        return self._executor

    # ---- inputs ----------------------------------------------------------------------------------
    def eligible_acquisitions(self, db: Session) -> list[DataAcquisition]:
        q = select(DataAcquisition).where(
            DataAcquisition.provider == "NISAR", DataAcquisition.product_type.in_(PROCESSABLE),
            DataAcquisition.local_file_path.is_not(None), DataAcquisition.status.in_(READY_STATUSES),
        ).order_by(DataAcquisition.acquisition_start.desc().nulls_last())
        return list(db.scalars(q))

    def list_samples(self) -> list[dict]:
        d = storage.samples_dir(self.settings.data_root)
        out = []
        for p in sorted(d.glob("*")) if d.exists() else []:
            if p.is_file() and not p.name.startswith("."):
                kind, fmt = detect_kind(p)
                out.append({"name": p.name, "product_kind": kind.value, "file_format": fmt, "size_bytes": p.stat().st_size})
        return out

    def resolve_input(self, db: Session, acquisition_id: uuid.UUID | None, sample_file: str | None
                      ) -> tuple[Path, DataOrigin, DataAcquisition | None, str, str]:
        """-> (path, origin, acquisition, input_kind, input_ref). Raises NotFound / ValidationFailed / ProcessingError."""
        if (acquisition_id is None) == (sample_file is None):
            raise ValidationFailed("provide exactly one of acquisition_id or sample_file")
        root = self.settings.data_root
        if acquisition_id is not None:
            acq = db.get(DataAcquisition, acquisition_id)
            if acq is None:
                raise NotFoundError(f"Acquisition {acquisition_id} not found")
            if acq.product_type not in PROCESSABLE or not acq.local_file_path or acq.status not in READY_STATUSES:
                raise ValidationFailed(
                    "acquisition is not processable: it needs a NISAR GUNW/GSLC/GCOV file on disk "
                    f"(status {acq.status}, product {acq.product_type}). Nothing is downloaded automatically."
                )
            try:
                path = storage.resolve_acquisition_file(root, acq.local_file_path)
            except FileNotFoundError:
                raise ValidationFailed("the file registered for this acquisition is missing on disk") from None
            except ProcessingError as exc:
                raise ValidationFailed(str(exc)) from None
            return path, DataOrigin.REAL_SATELLITE, acq, "ACQUISITION", acq.granule_id
        try:
            path = storage.resolve_sample(root, sample_file or "")
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from None
        except FileNotFoundError:
            raise NotFoundError("sample file not found in data/samples/insar") from None
        return path, DataOrigin.LOCAL_UNVERIFIED, None, "SAMPLE", path.name

    def inspect(self, db: Session, acquisition_id: uuid.UUID | None, sample_file: str | None) -> InspectionReport:
        path, origin, *_ = self.resolve_input(db, acquisition_id, sample_file)
        return inspect_product(path, origin)

    # ---- runs --------------------------------------------------------------------------------------
    def create_run(self, db: Session, acquisition_id: uuid.UUID | None, sample_file: str | None,
                   cfg: ProcessingConfig, *, force: bool = False) -> tuple[InSARProcessingRun, bool]:
        """-> (run, created). Duplicate (same input + config, active or completed) returns the existing run."""
        _, origin, acq, kind, ref = self.resolve_input(db, acquisition_id, sample_file)
        h = config_hash(ref, cfg)
        if not force:
            dup = db.scalars(select(InSARProcessingRun).where(
                InSARProcessingRun.config_hash == h,
                InSARProcessingRun.status.in_([s.value for s in _ACTIVE | {S.COMPLETED}]),
            ).order_by(InSARProcessingRun.created_at.desc())).first()
            if dup is not None:
                return dup, False
        run = InSARProcessingRun(
            acquisition_id=acq.id if acq else None, input_kind=kind, input_ref=ref, status=S.QUEUED.value,
            data_origin=origin.value, config=cfg.to_dict(), config_hash=h, stages=[], warnings=[],
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run, True

    def submit(self, run_id: uuid.UUID) -> None:
        self.executor.submit(self.execute, run_id)

    def cancel(self, db: Session, run_id: uuid.UUID) -> InSARProcessingRun:
        run = db.get(InSARProcessingRun, run_id, populate_existing=True)
        if run is None:
            raise NotFoundError(f"Processing run {run_id} not found")
        if S(run.status) in TERMINAL:
            raise ConflictError(f"run already {run.status}")
        run.cancel_requested = True
        if run.status in (S.PENDING.value, S.QUEUED.value):
            run.status, run.completed_at = S.CANCELLED.value, _now()
        db.commit()
        return run

    # ---- execution (synchronous; called from the executor or directly in tests) ---------------------
    def execute(self, run_id: uuid.UUID) -> None:
        s = self.sf()
        try:
            run = s.get(InSARProcessingRun, run_id, populate_existing=True)
            if run is None or S(run.status) in TERMINAL:
                return
            self._execute(s, run)
        except Exception:  # last resort: never leave a run hanging in an active state
            log.exception("insar run %s crashed", run_id)
            s.rollback()
            run = s.get(InSARProcessingRun, run_id, populate_existing=True)
            if run is not None and S(run.status) not in TERMINAL:
                self._finish(s, run, S.FAILED, "unexpected internal error (see server log)", None, None, ProcessingConfig())
        finally:
            s.close()

    def _stage(self, s: Session, run: InSARProcessingRun, name: S, status: str, message: str = "") -> None:
        stages = [dict(x) for x in run.stages]
        now = _now().isoformat()
        cur = next((x for x in stages if x["name"] == name.value), None)
        if cur is None:
            cur = {"name": name.value, "started_at": now}
            stages.append(cur)
        cur.update(status=status, message=message)
        if status != "RUNNING":
            cur["ended_at"] = now
        run.stages = stages
        if status == "RUNNING":
            run.status, run.current_stage = name.value, name.value
        s.commit()

    def _execute(self, s: Session, run: InSARProcessingRun) -> None:
        cfg = ProcessingConfig(**{k: v for k, v in run.config.items() if k in ProcessingConfig.__dataclass_fields__})
        started = _now()
        run.started_at = started
        rep: InspectionReport | None = None
        res = None
        tmp = None
        try:
            self._stage(s, run, S.INSPECTING, "RUNNING")
            try:
                path, origin, acq, _, _ = self.resolve_input(
                    s, run.acquisition_id, run.input_ref if run.input_kind == "SAMPLE" else None)
            except (NotFoundError, ValidationFailed) as exc:
                raise BlockedMissingInput(exc.message if hasattr(exc, "message") else str(exc)) from None
            rep = inspect_product(path, origin)
            run.inspection, run.product_kind, run.data_origin = rep.to_dict(), rep.product_kind.value, rep.data_origin.value
            self._stage(s, run, S.INSPECTING, "DONE", f"{rep.product_kind.value}; displacement supported: {rep.displacement_supported}")

            if rep.product_kind is ProductKind.UNKNOWN:
                raise ProcessingError("unrecognised or unsupported product")
            if rep.product_kind is ProductKind.S1_SLC:
                from app.services.insar.adapters.sentinel1_slc import Sentinel1SLCAdapter
                Sentinel1SLCAdapter().process()  # raises BlockedMissingInput with the real reason
            if rep.product_kind in (ProductKind.GSLC, ProductKind.GCOV):
                for st in (S.PREPROCESSING, S.DISPLACEMENT_CALCULATION):
                    self._stage(s, run, st, "SKIPPED", "; ".join(rep.displacement_blockers)[:300])
                self._finish(s, run, S.COMPLETED, None, rep, None, cfg,
                             extra=["inspection-only run: this product type cannot yield displacement; no raster produced"])
                return
            # GUNW: already geocoded and unwrapped, so no preprocessing is applied; only validation.
            self._stage(s, run, S.PREPROCESSING, "SKIPPED", "geocoded, unwrapped product: no re-processing applied")
            if not rep.displacement_supported:
                raise ProcessingError("displacement conversion is not supported by this file's metadata: "
                                      + "; ".join(rep.displacement_blockers))
            self._stage(s, run, S.DISPLACEMENT_CALCULATION, "RUNNING")
            out_dirs = {k: storage.run_dir(self.settings.data_root, storage.KIND_DIR[k], run.id) for k in ProductType}
            tmp = storage.run_dir(self.settings.data_root, "intermediate", run.id)
            last = [0.0]

            def progress(frac: float) -> None:
                if time.monotonic() - last[0] > 0.5:
                    last[0] = time.monotonic()
                    s.refresh(run)  # picks up cancel_requested set from another session
                    run.progress = round(frac, 3)
                    s.commit()

            res = process_gunw(
                path, rep, cfg, out_dirs=out_dirs, tmp_dir=tmp, min_free_bytes=self.settings.insar_min_free_disk_bytes,
                progress=progress, cancelled=lambda: bool(run.cancel_requested),
            )
            self._stage(s, run, S.DISPLACEMENT_CALCULATION, "DONE", f"{len(res.outputs)} raster(s) written")
            self._stage(s, run, S.QUALITY_CHECK, "RUNNING")
            self._register(s, run, rep, res)
            self._stage(s, run, S.QUALITY_CHECK, "DONE")
            run.progress = 1.0
            self._finish(s, run, S.COMPLETED, None, rep, res, cfg)
        except Cancelled:
            self._finish(s, run, S.CANCELLED, "cancelled by user", rep, res, cfg)
        except BlockedMissingInput as exc:
            self._finish(s, run, S.BLOCKED_MISSING_INPUT, str(exc), rep, res, cfg)
        except ProcessingError as exc:
            self._finish(s, run, S.FAILED, str(exc), rep, res, cfg)
        finally:
            if tmp is not None and not cfg.keep_intermediates:
                shutil.rmtree(tmp, ignore_errors=True)

    def _register(self, s: Session, run: InSARProcessingRun, rep: InspectionReport, res) -> None:
        root = self.settings.data_root
        for o in res.outputs:
            p = Path(o.path)
            b = o.extra.get("bounds_4326")
            s.add(DeformationProduct(
                run_id=run.id, acquisition_id=run.acquisition_id, product_type=o.kind.value,
                file_path=storage.to_relative(root, p), file_size_bytes=p.stat().st_size, units=o.units,
                crs=o.crs, width=o.width, height=o.height, reference_time=rep.reference_time,
                secondary_time=rep.secondary_time, data_origin=rep.data_origin.value,
                sign_convention=o.extra.get("sign_convention"), scientifically_validated=False,
                statistics=o.stats, footprint=from_shape(box(*b), srid=4326) if b else None,
            ))
        s.commit()

    def _finish(self, s: Session, run: InSARProcessingRun, status: S, error: str | None,
                rep: InspectionReport | None, res, cfg: ProcessingConfig, extra: list[str] | None = None) -> None:
        ended = _now()
        run.stages = [{**x, "status": "ABORTED", "ended_at": ended.isoformat()} if x.get("status") == "RUNNING" else x
                      for x in run.stages]
        file_integrity = None
        if run.acquisition_id:
            acq = s.get(DataAcquisition, run.acquisition_id)
            vr = (acq.validation_report or {}) if acq else {}
            file_integrity = {"phase2_status": acq.status if acq else None, "passed": vr.get("passed"),
                              "note": "file integrity only, not scientific validation"} if acq else None
        report = quality_report(
            rep=rep, cfg=cfg, result=res, status=status.value, started=run.started_at or ended, ended=ended,
            input_ref=run.input_ref, errors=[error] if error else [], extra_warnings=extra, file_integrity=file_integrity,
        )
        root = self.settings.data_root
        try:
            write_json(storage.run_dir(root, "quality_reports", run.id) / "quality_report.json", report)
            if rep is not None:
                write_json(storage.run_dir(root, "inspections", run.id) / "inspection.json", rep.to_dict())
            write_json(storage.run_dir(root, "metadata", run.id) / "processing_metadata.json", {
                "run_id": str(run.id), "input_ref": run.input_ref, "config": cfg.to_dict(), "status": status.value,
                "outputs": [{"kind": o.kind.value, "file": Path(o.path).name, "units": o.units} for o in (res.outputs if res else [])],
            })
        except OSError:
            log.exception("could not write run metadata files for %s", run.id)
        run.quality_report, run.warnings = report, report["warnings"]
        run.status, run.error_message, run.completed_at, run.current_stage = status.value, error, ended, None
        s.commit()

    def recover_stale_runs(self) -> int:
        """In-process queue is lost on restart: mark unfinished runs FAILED (they can be re-created)."""
        with self.sf() as s:
            rows = list(s.scalars(select(InSARProcessingRun).where(
                InSARProcessingRun.status.in_([x.value for x in _ACTIVE]))))
            for r in rows:
                r.status, r.error_message, r.completed_at = S.FAILED.value, "interrupted by a server restart; create a new run", _now()
            s.commit()
            return len(rows)

    # ---- queries ------------------------------------------------------------------------------------
    @staticmethod
    def count(db: Session, model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0
