"""CLI for Phase 2. Commands are pure functions over (args, services, out) so they are testable with fakes.

Exit codes: 0 ok, 1 operation finished but failed (validation / download), 2 usage or validation error,
3 provider / network error, 4 Earthdata credentials missing.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must run before any geo library)

import argparse
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import Settings
from app.models import DataAcquisition, DownloadJob, DataCollection
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.environmental import acquire_environmental
from app.services.data_acquisition.metadata_service import MetadataRegistrationService
from app.services.data_acquisition.orchestrator import AUTH_MESSAGE, AcquisitionOrchestrator
from app.services.data_acquisition.providers import landslide_catalog as lc
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.status_service import compute_status
from app.services.data_acquisition.types import (
    AuthenticationError, DataAcquisitionError, Maturity, ProviderError, SearchQuery)

OK, FAILED, USAGE, PROVIDER, AUTH = 0, 1, 2, 3, 4
AOI_HELP = (
    "No AOI given and none found. Pass --aoi FILE (GeoJSON or WKT), or put exactly one file in {dir}. "
    "See docs/aoi-configuration.md."
)


@dataclass
class Services:
    settings: Settings
    auth: Any
    search: AcquisitionSearchService
    orchestrator: AcquisitionOrchestrator
    session_factory: Callable[[], Any]


def build_services() -> Services:
    from app.api.v1.data import deps
    from app.core.config import get_settings
    from app.database.session import SessionLocal

    s = get_settings()
    return Services(
        s, deps.get_auth(), deps.get_search_service(), deps.get_orchestrator(), SessionLocal)


Out = Callable[[str], None]


# ---- helpers ------------------------------------------------------------------------------
def _date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        d = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"invalid date {text!r}; use YYYY-MM-DD") from None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _aoi(args, svc: Services) -> AOI:
    if args.aoi:
        return AOI.from_file(args.aoi, args.name)
    folder = svc.settings.aoi_directory
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".geojson", ".json", ".wkt")) if folder.is_dir() else []
    if len(files) != 1:
        raise ValueError(AOI_HELP.format(dir=folder) + (f" Found {len(files)} files: {[f.name for f in files]}." if files else ""))
    return AOI.from_file(files[0], args.name)


def _table(rows: list[list[Any]], headers: list[str], out: Out) -> None:
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    for r in [headers, *rows]:
        out("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def _day(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%d") if d else "-"


def _need_auth(svc: Services, out: Out) -> bool:
    if svc.auth.status() == "missing":
        out(AUTH_MESSAGE + " Searching and listing work without credentials; only downloads need them.")
        return False
    return True


def _results(results, out: Out) -> None:
    _table([[r.granule_id, r.product_type, r.maturity, _day(r.acquisition_start), r.file_size_bytes, r.status,
             r.data_kind] for r in results],
           ["granule_id", "product", "maturity", "date", "size_bytes", "status", "data"], out)


def _notes(warnings, errors, out: Out) -> None:
    for w in warnings:
        out(f"warning: {w}")
    for name, e in errors.items():
        out(f"error: {name}: {e}")


def _wait(svc: Services, job_ids: list[uuid.UUID], out: Out, sleep: Callable[[float], None] = time.sleep) -> int:
    """Poll jobs (run by the orchestrator executor) until all finish, printing a progress line."""
    code = OK
    for jid in job_ids:
        while True:
            with svc.session_factory() as s:
                job = s.get(DownloadJob, jid, populate_existing=True)
                snap = (job.status, job.progress, job.bytes_downloaded, job.error_message, job.acquisition.granule_id)
            status, prog, nbytes, err, gid = snap
            if status in ("COMPLETED", "FAILED"):
                break
            out(f"{gid}: {status} {prog * 100:5.1f}% ({nbytes} bytes)")
            sleep(1.0)
        out(f"{gid}: {status}" + (f" - {err}" if err else ""))
        if status == "FAILED":
            code = max(code, AUTH if err == AUTH_MESSAGE else PROVIDER)
    return code


# ---- commands -----------------------------------------------------------------------------
def cmd_discover(args, svc: Services, out: Out = print) -> int:
    aoi = _aoi(args, svc)
    query = SearchQuery(
        aoi=aoi, start=_date(args.start_date), end=_date(args.end_date), product_types=tuple(args.products),
        maturities=tuple(Maturity(m) for m in args.maturities), max_results=args.max_results)
    found = svc.search.search(query, provider_names=["NISAR"], register=not args.dry_run)
    _results(found.results, out)
    _notes(found.warnings, found.provider_errors, out)
    out(f"{len(found.results)} granule(s) found for {aoi.name}. " + (
        "Dry run: nothing registered." if args.dry_run else "Registered as metadata only; nothing downloaded."))
    return PROVIDER if found.provider_errors and not found.results else OK


def cmd_download(args, svc: Services, out: Out = print, sleep: Callable[[float], None] = time.sleep) -> int:
    with svc.session_factory() as s:
        q = select(DataAcquisition).where(DataAcquisition.granule_id == args.granule_id)
        if args.provider:
            q = q.where(DataAcquisition.provider == args.provider.upper())
        acqs = list(s.scalars(q))
    if not acqs:
        out(f"Granule {args.granule_id} is not registered. Run `discover` (without --dry-run) first.")
        return USAGE
    if len(acqs) > 1:
        out(f"{args.granule_id} matches several providers; pass --provider.")
        return USAGE
    if not _need_auth(svc, out):
        return AUTH
    plan = svc.orchestrator.plan_jobs([acqs[0].id])
    for reason in plan.skipped.values():
        out(f"not queued: {reason}")
    if not plan.jobs:
        return OK if all(r.startswith("already") for r in plan.skipped.values()) else USAGE
    return _wait(svc, [j.id for j in plan.jobs], out, sleep)


def cmd_acquire_environmental(args, svc: Services, out: Out = print, sleep: Callable[[float], None] = time.sleep) -> int:
    start, end = _date(args.start_date), _date(args.end_date)
    if start > end:
        raise ValueError("start-date must not be after end-date")
    if args.execute and not _need_auth(svc, out):
        return AUTH
    res = acquire_environmental(
        svc.search, svc.orchestrator, svc.settings, _aoi(args, svc), start, end,
        include_smap=args.include_smap, dry_run=not args.execute, max_granules=args.max_granules)
    _results(res.results, out)
    _notes(res.warnings, res.provider_errors, out)
    if not args.execute:
        out("Dry run: nothing registered or downloaded. Use --execute to do so.")
        return PROVIDER if res.provider_errors and not res.results else OK
    return _wait(svc, [j.id for j in res.jobs], out, sleep)


def cmd_import_landslides(args, svc: Services, out: Out = print) -> int:
    try:
        with svc.session_factory() as s:
            r = lc.LandslideCatalogProvider(svc.settings, s).run_import(args.force_download, args.file)
    except RuntimeError as exc:  # download failed after retries
        out(f"error: {exc}")
        return PROVIDER
    except OSError as exc:
        out(f"error: cannot read file: {exc}")
        return USAGE
    out(f"version {r.dataset_version}: inserted {r.inserted}, updated {r.updated}, skipped invalid {r.skipped_invalid}")
    out(f"source: {r.source_file}")
    out(f"note: {r.limitations}")
    return OK


def cmd_status(args, svc: Services, out: Out = print) -> int:
    with svc.session_factory() as s:
        st = compute_status(svc.settings, svc.auth, svc.search.providers, s)
    _table([[p.name, p.enabled, p.authentication, p.collections_discovered, p.note] for p in st.providers],
           ["provider", "enabled", "auth", "collections", "note"], out)
    out(f"earthdata credentials configured: {st.earthdata_credentials_configured}")
    out(f"acquisitions registered: {st.acquisitions_registered}; files downloaded: {st.files_downloaded}; "
        f"file-validated: {st.files_validated}")
    out(f"jobs failed: {st.jobs_failed}; active: {st.jobs_active}; landslide events: {st.landslide_events}")
    out(f"products: {st.product_distribution}")
    out(f"data root: {st.data_root}; free bytes: {st.storage_free_bytes}; used (raw): {st.storage_used_bytes}")
    return OK


def cmd_history(args, svc: Services, out: Out = print) -> int:
    with svc.session_factory() as s:
        rows, total = MetadataRegistrationService(s).list_acquisitions(
            status=args.status, product_type=args.product, limit=args.limit)
        _table([[a.granule_id, a.provider, a.product_type, a.status, a.retrieved_at and _day(a.retrieved_at),
                 a.error_message] for a in rows],
               ["granule_id", "provider", "product", "status", "retrieved", "error"], out)
    out(f"{len(rows)} of {total} shown")
    return OK


def cmd_retry(args, svc: Services, out: Out = print, sleep: Callable[[float], None] = time.sleep) -> int:
    if not _need_auth(svc, out):
        return AUTH
    try:
        svc.orchestrator.retry_job(uuid.UUID(args.job_id))
    except LookupError:
        out(f"job {args.job_id} not found")
        return USAGE
    return _wait(svc, [uuid.UUID(args.job_id)], out, sleep)


def cmd_revalidate(args, svc: Services, out: Out = print) -> int:
    try:
        acq = svc.orchestrator.revalidate(uuid.UUID(args.acquisition_id))
    except LookupError:
        out(f"acquisition {args.acquisition_id} not found")
        return USAGE
    out(f"{acq.granule_id}: {acq.status}" + (f" - {acq.error_message}" if acq.error_message else ""))
    out("note: file-format checks only, not a scientific validation.")
    return OK if acq.status == "VALIDATED" else FAILED


def cmd_collections(args, svc: Services, out: Out = print) -> int:
    if args.discover:
        found, warnings = svc.search.discover_collections()
        _notes(warnings, {}, out)
        if not found:
            out("no collections discovered (see warnings)")
    with svc.session_factory() as s:
        cols = list(s.scalars(select(DataCollection).order_by(DataCollection.provider, DataCollection.collection_short_name)))
    _table([[c.provider, c.collection_short_name, c.version, c.product_type, c.maturity, c.cmr_concept_id]
            for c in cols], ["provider", "short_name", "version", "product", "maturity", "concept_id"], out)
    if not cols:
        out("no collections stored yet; run `collections --discover` (no credentials needed).")
    return OK


# ---- parser / entry -----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="PRECURSOR AI data acquisition")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=fn)
        return sp

    def aoi_args(sp, dates_required=False):
        sp.add_argument("--aoi", help="GeoJSON/WKT file (default: the single file in the AOI directory)")
        sp.add_argument("--name")
        sp.add_argument("--start-date", required=dates_required)
        sp.add_argument("--end-date", required=dates_required)

    sp = add("discover", cmd_discover, "search NISAR granules (metadata only)")
    aoi_args(sp)
    sp.add_argument("--products", nargs="+", default=["GUNW", "GCOV", "GSLC"])
    sp.add_argument("--maturities", nargs="+", default=["VALIDATED"], choices=[m.value for m in Maturity])
    sp.add_argument("--max-results", type=int, default=10)
    sp.add_argument("--dry-run", action="store_true", help="do not register results")

    sp = add("download", cmd_download, "download one registered granule in the foreground")
    sp.add_argument("--granule-id", required=True)
    sp.add_argument("--provider")

    sp = add("acquire-environmental", cmd_acquire_environmental, "NASADEM + GPM (+ SMAP); dry run unless --execute")
    aoi_args(sp, dates_required=True)
    sp.add_argument("--include-smap", action="store_true")
    sp.add_argument("--max-granules", type=int, default=10)
    sp.add_argument("--execute", action="store_true", help="register and download (default: dry run)")

    sp = add("import-landslides", cmd_import_landslides, "import the NASA Global Landslide Catalog")
    sp.add_argument("--file", help="import a local CSV instead of downloading")
    sp.add_argument("--force-download", action="store_true")

    add("status", cmd_status, "pipeline status")
    sp = add("history", cmd_history, "registered granules and their status")
    sp.add_argument("--status")
    sp.add_argument("--product")
    sp.add_argument("--limit", type=int, default=50)
    sp = add("retry", cmd_retry, "retry a FAILED download job")
    sp.add_argument("job_id")
    sp = add("revalidate", cmd_revalidate, "re-run file checks on a downloaded acquisition")
    sp.add_argument("acquisition_id")
    sp = add("collections", cmd_collections, "list verified collections (no AOI or credentials needed)")
    sp.add_argument("--discover", action="store_true", help="query the live catalog and store the result")
    return p


def run(args, svc: Services, out: Out = print) -> int:
    """Run one parsed command and map errors to exit codes."""
    try:
        return args.func(args, svc, out)
    except AuthenticationError as exc:
        out(f"error: {exc}")
        return AUTH
    except (ProviderError, ConnectionError, TimeoutError) as exc:
        out(f"error: {exc}")
        return PROVIDER
    except ValueError as exc:  # includes AOIError, bad dates, bad ids
        out(f"error: {exc}")
        return USAGE
    except DataAcquisitionError as exc:
        out(f"error: {exc}")
        return PROVIDER


def main(argv: list[str] | None = None, services: Callable[[], Services] = build_services) -> int:
    args = build_parser().parse_args(argv)  # argparse exits 2 on usage errors
    return run(args, services())
