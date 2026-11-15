"""NASA Global Landslide Catalog (Open Data Portal export) importer and query helpers.

HISTORICAL REFERENCE ONLY. Not a granule provider: it loads point events into `landslide_events`.

Verified against the NASA Open Data Portal (CKAN package_show for `global-landslide-catalog-export`):
the CSV resource is SOURCE_URL below. Its header row is
  source_name,source_link,event_id,event_date,event_time,event_title,event_description,
  location_description,location_accuracy,landslide_category,landslide_trigger,landslide_size,
  landslide_setting,fatality_count,injury_count,storm_name,photo_link,notes,event_import_source,
  event_import_id,country_name,country_code,admin_division_name,admin_division_population,
  gazeteer_closest_point,gazeteer_distance,submitted_date,created_date,last_edited_date,longitude,latitude
Dates look like "08/01/2008 12:00:00 AM" (Socrata export, read as MM/DD/YYYY, UTC).
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, shape
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.data_collection import DataCollection
from app.models.landslide_event import LandslideEvent
from app.schemas import data_acquisition as schemas
from app.services.data_acquisition.storage import ensure_layout

log = logging.getLogger(__name__)

DATASET_PAGE_URL = "https://data.nasa.gov/dataset/global-landslide-catalog-export"
SOURCE_URL = "https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv"
EXPORT_DATE = "2017-09-28"  # date of the last event in the export (M1 census, ml/reports/M1_census_and_download_list.md)
DEFAULT_VERSION = "export-2016-03-07"  # legacy identifier kept as-is: it is stored in the DB default/migration and file names
DATASET_NOTE = (
    "NASA Open Data Portal export, a historical one-time export whose last event is dated 2017-09-28; "
    "NOT a complete or current landslide inventory; absence of an event is not evidence that no landslide occurred."
)
LIMITATIONS = DATASET_NOTE
COLLECTION_SHORT_NAME = "NASA_GLOBAL_LANDSLIDE_CATALOG_EXPORT"

REQUIRED = ("event_id", "latitude", "longitude")
BATCH = 1000
MAX_ERRORS = 50
_DATE_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
)


@dataclass
class ImportResult:
    inserted: int = 0
    updated: int = 0
    skipped_invalid: int = 0
    bad_dates: int = 0
    errors: list[str] = field(default_factory=list)
    dataset_version: str = DEFAULT_VERSION
    source_file: str = ""
    sha256: str = ""


def _norm(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def parse_date(raw: str | None) -> datetime | None:
    raw = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_coords(lat_raw: str, lon_raw: str) -> tuple[float, float] | None:
    """(lat, lon) or None. Empty, non-numeric, non-finite, out-of-range and exactly (0, 0) are invalid:
    (0, 0) is the usual placeholder for a missing location, and a landslide at Null Island is not plausible."""
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or abs(lat) > 90 or abs(lon) > 180:
        return None
    if lat == 0 and lon == 0:
        return None
    return lat, lon


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LandslideCatalogProvider:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        http_session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.db = session
        self.http = http_session or requests.Session()
        self._sleep = sleep

    # ---- download -------------------------------------------------------------------------
    def fetch(self, dest_dir: Path | None = None, force: bool = False) -> Path:
        dest_dir = dest_dir or (self.settings.data_root / "raw" / "landslide_catalog")
        ensure_layout(self.settings.data_root)
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        base = f"global_landslide_catalog_{DEFAULT_VERSION}__retrieved_{now:%Y%m%d}"
        target = dest_dir / f"{base}.csv"
        if target.exists():
            if not force:
                log.info("reusing existing catalog file %s", target)
                return target
            target = dest_dir / f"{base}_{now:%H%M%S%f}.csv"  # keep both; never overwrite

        tmp = target.with_name(target.name + ".part")
        attempts = max(1, self.settings.download_retries)
        for attempt in range(1, attempts + 1):
            try:
                resp = self.http.get(SOURCE_URL, stream=True, timeout=self.settings.request_timeout_s)
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                break
            except requests.RequestException as exc:
                tmp.unlink(missing_ok=True)
                if attempt == attempts:
                    raise RuntimeError(f"landslide catalog download failed after {attempts} attempts: {exc}") from exc
                self._sleep(2 ** attempt)
        os.replace(tmp, target)
        target.with_name(target.name + ".sha256").write_text(f"{_sha256(target)}  {target.name}\n")
        return target

    # ---- import ---------------------------------------------------------------------------
    def import_file(
        self, path: Path, *, dataset_version: str | None = None, retrieved_at: datetime | None = None
    ) -> ImportResult:
        path = Path(path)
        version = dataset_version or DEFAULT_VERSION
        retrieved_at = retrieved_at or datetime.now(timezone.utc)
        res = ImportResult(dataset_version=version, source_file=str(path), sha256=_sha256(path))

        def err(msg: str) -> None:
            res.skipped_invalid += 1
            if len(res.errors) < MAX_ERRORS:
                res.errors.append(msg)

        batch: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        total_rows = 0
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            cols = {_norm(h): h for h in headers}
            missing = [c for c in REQUIRED if c not in cols]
            if missing:
                raise ValueError(f"missing required column(s) {missing}; headers found: {headers}")
            g = lambda row, name: (row.get(cols[name]) or "").strip() if name in cols else ""  # noqa: E731

            for lineno, row in enumerate(reader, start=2):
                total_rows += 1
                eid = g(row, "event_id")
                if not eid or len(eid) > 60:
                    err(f"line {lineno}: invalid event_id {eid!r}")
                    continue
                coords = parse_coords(g(row, "latitude"), g(row, "longitude"))
                if coords is None:
                    err(f"line {lineno}: event {eid}: invalid coordinates "
                        f"lat={g(row, 'latitude')!r} lon={g(row, 'longitude')!r}")
                    continue
                if eid in seen:
                    err(f"line {lineno}: duplicate event_id {eid} (first occurrence kept)")
                    continue
                seen.add(eid)
                date_raw = g(row, "event_date")
                event_date = parse_date(date_raw)
                if date_raw and event_date is None:
                    res.bad_dates += 1
                source = g(row, "source_name") or None
                if source and g(row, "source_link"):
                    source = f"{source} ({g(row, 'source_link')})"
                lat, lon = coords
                batch[eid] = dict(
                    id=uuid.uuid4(),
                    external_event_id=eid,
                    event_date=event_date,
                    location_name=g(row, "location_description") or g(row, "event_title") or None,
                    country=g(row, "country_name")[:100] or None,
                    trigger=g(row, "landslide_trigger")[:100] or None,
                    landslide_type=g(row, "landslide_category")[:100] or None,
                    source=source,
                    geometry=from_shape(Point(lon, lat), srid=4326),
                    original_attributes={k: v for k, v in row.items() if k is not None},
                    dataset_version=version,
                    retrieved_at=retrieved_at,
                )
                if len(batch) >= BATCH:
                    self._flush(batch, version, res)
                    batch = {}
            if batch:
                self._flush(batch, version, res)

        if res.bad_dates:
            log.warning("%d rows had unparseable event_date (stored as NULL)", res.bad_dates)
        self._upsert_collection(res, retrieved_at, total_rows)
        self.db.commit()
        return res

    def _flush(self, batch: dict[str, dict[str, Any]], version: str, res: ImportResult) -> None:
        existing = set(self.db.scalars(
            select(LandslideEvent.external_event_id).where(
                LandslideEvent.dataset_version == version, LandslideEvent.external_event_id.in_(list(batch))
            )
        ))
        stmt = pg_insert(LandslideEvent).values(list(batch.values()))
        update_cols = {c: stmt.excluded[c] for c in (
            "event_date", "location_name", "country", "trigger", "landslide_type", "source",
            "geometry", "original_attributes", "retrieved_at")}
        self.db.execute(stmt.on_conflict_do_update(constraint="uq_event_id_version", set_=update_cols))
        res.updated += len(existing)
        res.inserted += len(batch) - len(existing)

    def _upsert_collection(self, res: ImportResult, retrieved_at: datetime, row_count: int) -> None:
        meta = {
            "limitations": DATASET_NOTE, "export_current_as_of": EXPORT_DATE, "source_url": SOURCE_URL,
            "retrieved_at": retrieved_at.isoformat(), "sha256": res.sha256, "row_count": row_count,
        }
        col = self.db.scalar(select(DataCollection).where(
            DataCollection.collection_short_name == COLLECTION_SHORT_NAME,
            DataCollection.version == res.dataset_version))
        if col is None:
            col = DataCollection(collection_short_name=COLLECTION_SHORT_NAME, version=res.dataset_version)
            self.db.add(col)
        col.provider = "LANDSLIDE_CATALOG"
        col.dataset_name = "NASA Global Landslide Catalog (Open Data Portal export)"
        col.product_type = "LANDSLIDE_EVENTS"
        col.maturity = None
        col.description = DATASET_NOTE
        col.documentation_url = DATASET_PAGE_URL
        col.metadata_json = meta

    def run_import(self, force_download: bool = False, file_path: str | Path | None = None,
                   allowed_root: Path | None = None) -> schemas.LandslideImportResponse:
        """`allowed_root` (set by the API) confines a caller-supplied `file_path` to that directory tree: the API must never read arbitrary
        server paths (Phase 2 issue 1). The local CLI passes None because the operator already has file access."""
        if file_path and allowed_root is not None:
            root = Path(allowed_root).resolve()
            resolved = Path(file_path).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("file_path must be inside the configured data root")
        path = Path(file_path) if file_path else self.fetch(force=force_download)
        res = self.import_file(path)
        return schemas.LandslideImportResponse(
            dataset_version=res.dataset_version, inserted=res.inserted, updated=res.updated,
            skipped_invalid=res.skipped_invalid, source_file=res.source_file, limitations=LIMITATIONS,
        )


# ---- queries (used by the API) -----------------------------------------------------------------
def list_events(
    session: Session,
    *,
    bbox: tuple[float, float, float, float] | None = None,  # min_lon, min_lat, max_lon, max_lat
    aoi_geometry: dict | None = None,  # GeoJSON, EPSG:4326
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    country: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[LandslideEvent], int]:
    q = select(LandslideEvent)
    if bbox:
        q = q.where(func.ST_Intersects(LandslideEvent.geometry, func.ST_MakeEnvelope(*bbox, 4326)))
    if aoi_geometry:
        q = q.where(func.ST_Intersects(LandslideEvent.geometry, from_shape(shape(aoi_geometry), srid=4326)))
    if date_from:
        q = q.where(LandslideEvent.event_date >= date_from)
    if date_to:
        q = q.where(LandslideEvent.event_date <= date_to)
    if country:
        q = q.where(func.lower(LandslideEvent.country) == country.strip().lower())
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(
        q.order_by(LandslideEvent.event_date.desc().nulls_last(), LandslideEvent.external_event_id)
        .limit(limit).offset(offset)
    ).all()
    return list(rows), total


def to_read_schema(row: LandslideEvent) -> schemas.LandslideEventRead:
    pt = to_shape(row.geometry)
    return schemas.LandslideEventRead(
        id=row.id, external_event_id=row.external_event_id, event_date=row.event_date,
        location_name=row.location_name, country=row.country, trigger=row.trigger,
        landslide_type=row.landslide_type, source=row.source, longitude=pt.x, latitude=pt.y,
        original_attributes=row.original_attributes, dataset_version=row.dataset_version,
    )
