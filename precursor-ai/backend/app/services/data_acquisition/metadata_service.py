"""Registers catalog metadata in PostgreSQL. Registration records that a granule EXISTS in the catalog;
it never implies the file was downloaded or validated."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.data_acquisition import GranuleResult
from app.models.data_acquisition import DataAcquisition
from app.models.data_collection import DataCollection
from app.models.download_job import DownloadJob
from app.services.data_acquisition import storage
from app.services.data_acquisition.types import (
    AcquisitionStatus,
    CollectionInfo,
    GranuleRecord,
    Maturity,
    ProviderName,
)

S = AcquisitionStatus
_REFRESHABLE = {S.DISCOVERED.value, S.FAILED.value}


def scrub(message: object, settings: Any = None) -> str:
    """Strip URL query strings and configured Earthdata credentials from a message."""
    text = re.sub(r"\?[^\s'\"]+", "?<redacted>", str(message))
    for attr in ("earthdata_username", "earthdata_password"):
        secret = getattr(settings, attr, None)
        value = secret.get_secret_value() if secret else ""
        if value:
            text = text.replace(value, "<redacted>")
    return text


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)))


def _baseline_days(meta: dict[str, Any]) -> float | None:
    try:
        vals = [v if isinstance(v, datetime) else datetime.fromisoformat(v) for v in
                (meta.get("reference_start"), meta.get("secondary_start"))]
    except (TypeError, ValueError):
        return None
    return abs((vals[1] - vals[0]).total_seconds()) / 86400


def _strip_query(url: str | None) -> str | None:
    if not url:
        return url
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class MetadataRegistrationService:
    def __init__(self, session: Session):
        self.session = session

    # ---- collections ---------------------------------------------------------------
    def _collection(self, short_name: str, version: str) -> DataCollection | None:
        return self.session.scalar(
            select(DataCollection).where(
                DataCollection.collection_short_name == short_name, DataCollection.version == version
            )
        )

    def upsert_collection(self, info: CollectionInfo) -> DataCollection:
        col = self._collection(info.short_name, info.version)
        if col is None:
            col = DataCollection(collection_short_name=info.short_name, version=info.version)
            self.session.add(col)
        col.provider = info.provider.value
        col.dataset_name = info.dataset_name
        col.product_type = info.product_type
        col.maturity = info.maturity.value if info.maturity else None
        col.description = info.description
        col.documentation_url = info.documentation_url
        col.cmr_concept_id = info.concept_id
        col.metadata_json = json_safe(info.extra)
        self.session.commit()
        return col

    def ensure_collection(self, record: GranuleRecord) -> DataCollection:
        """Collection of a granule the catalog just returned; created minimally if not yet discovered."""
        col = self._collection(record.collection_short_name, record.version)
        if col:
            return col
        return self.upsert_collection(CollectionInfo(
            provider=record.provider, short_name=record.collection_short_name,
            dataset_name=record.collection_short_name, product_type=record.product_type,
            version=record.version, maturity=record.maturity,
        ))

    # ---- granules ------------------------------------------------------------------
    def existing_by_granule_ids(self, provider: ProviderName | str, ids: list[str]) -> dict[str, DataAcquisition]:
        if not ids:
            return {}
        rows = self.session.scalars(
            select(DataAcquisition).where(
                DataAcquisition.provider == str(getattr(provider, "value", provider)),
                DataAcquisition.granule_id.in_(ids),
            )
        )
        return {r.granule_id: r for r in rows}

    @staticmethod
    def _apply_catalog(acq: DataAcquisition, rec: GranuleRecord) -> None:
        acq.product_type = rec.product_type
        acq.acquisition_start, acq.acquisition_end = rec.acquisition_start, rec.acquisition_end
        acq.processing_date = rec.processing_date
        acq.orbit_direction, acq.relative_orbit = rec.orbit_direction, rec.relative_orbit
        acq.spatial_footprint = from_shape(rec.footprint, srid=4326) if rec.footprint is not None else None
        acq.crs = rec.crs
        acq.file_format, acq.file_size_bytes, acq.download_url = rec.file_format, rec.file_size_bytes, rec.download_url
        acq.maturity = rec.maturity.value if rec.maturity else None
        meta = json_safe(rec.metadata)
        if rec.checksum:
            meta["published_checksum"] = {"value": rec.checksum, "algorithm": rec.checksum_algorithm}
        acq.metadata_json = meta
        if not acq.local_file_path:  # once a file landed, `checksum` is ours (SHA-256), not the published one
            acq.checksum, acq.checksum_algorithm = rec.checksum, rec.checksum_algorithm

    def register_granule(
        self, record: GranuleRecord, collection: DataCollection, monitored_area_id: uuid.UUID | None = None
    ) -> tuple[DataAcquisition, bool]:
        provider = record.provider.value
        acq = self.existing_by_granule_ids(provider, [record.granule_id]).get(record.granule_id)
        created = acq is None
        if created:
            acq = DataAcquisition(provider=provider, granule_id=record.granule_id, status=S.DISCOVERED.value)
        if created or acq.status in _REFRESHABLE:  # never rewrite rows that advanced past discovery
            self._apply_catalog(acq, record)
            acq.collection_id = collection.id
        if monitored_area_id and acq.monitored_area_id is None:
            acq.monitored_area_id = monitored_area_id
        self.session.add(acq)
        try:
            self.session.commit()
        except IntegrityError:  # concurrent registration of the same granule: keep the winner's row
            self.session.rollback()
            return self.existing_by_granule_ids(provider, [record.granule_id])[record.granule_id], False
        return acq, created

    # ---- status transitions --------------------------------------------------------
    def set_status(self, acq: DataAcquisition, status: AcquisitionStatus, error: str | None = None) -> None:
        acq.status = status.value
        acq.error_message = error
        self.session.commit()

    def mark_downloaded(self, acq: DataAcquisition, path: Path | str, sha256: str | None, size: int) -> None:
        """File is complete on disk. NOT validated yet. sha256 may be None until validation computes it."""
        acq.local_file_path = str(path)
        if sha256:
            acq.checksum, acq.checksum_algorithm = sha256, "SHA-256"
        acq.file_size_bytes = size
        acq.retrieved_at = datetime.now(UTC)
        acq.status = S.DOWNLOADED.value
        acq.error_message = None
        self.session.commit()

    def to_record(self, acq: DataAcquisition) -> GranuleRecord:
        """Rebuild a catalog record from the DB row (for providers/validators)."""
        pub = (acq.metadata_json or {}).get("published_checksum") or {}
        return GranuleRecord(
            provider=ProviderName(acq.provider), granule_id=acq.granule_id,
            collection_short_name=acq.collection.collection_short_name, product_type=acq.product_type,
            version=acq.collection.version, maturity=Maturity(acq.maturity) if acq.maturity else None,
            acquisition_start=acq.acquisition_start, acquisition_end=acq.acquisition_end,
            footprint=to_shape(acq.spatial_footprint) if acq.spatial_footprint is not None else None,
            processing_date=acq.processing_date, orbit_direction=acq.orbit_direction,
            relative_orbit=acq.relative_orbit, file_format=acq.file_format, file_size_bytes=acq.file_size_bytes,
            download_url=acq.download_url, checksum=pub.get("value"), checksum_algorithm=pub.get("algorithm"),
            crs=acq.crs, metadata=dict(acq.metadata_json or {}),
        )

    # ---- API shaping ---------------------------------------------------------------
    def to_granule_result(self, obj: DataAcquisition | GranuleRecord, acq: DataAcquisition | None = None) -> GranuleResult:
        """`obj` is a row or a fresh record; pass `acq` to attach registration info to a record."""
        row = obj if isinstance(obj, DataAcquisition) else acq
        if isinstance(obj, DataAcquisition):
            fp = to_shape(obj.spatial_footprint) if obj.spatial_footprint is not None else None
            short, version = obj.collection.collection_short_name, obj.collection.version
        else:
            fp, short, version = obj.footprint, obj.collection_short_name, obj.version
        status = row.status if row else S.DISCOVERED.value
        kind = "validated" if status == S.VALIDATED.value else (
            "downloaded" if row and row.local_file_path else "metadata_only")
        return GranuleResult(
            provider=obj.provider if isinstance(obj.provider, str) else obj.provider.value,
            granule_id=obj.granule_id, collection_short_name=short, product_type=obj.product_type, version=version,
            maturity=(m.value if isinstance(m := obj.maturity, Maturity) else m),
            acquisition_start=obj.acquisition_start, acquisition_end=obj.acquisition_end,
            temporal_baseline_days=_baseline_days(obj.metadata if isinstance(obj, GranuleRecord) else obj.metadata_json or {}),
            orbit_direction=obj.orbit_direction, relative_orbit=obj.relative_orbit, file_format=obj.file_format,
            file_size_bytes=obj.file_size_bytes, footprint=mapping(fp) if fp is not None else None,
            registered=row is not None, acquisition_id=row.id if row else None, status=status, data_kind=kind,
        )

    # ---- provenance manifests (no credentials, no URL query strings) ---------------
    def write_manifest(self, acq: DataAcquisition, data_root: Path) -> Path:
        col = acq.collection
        base = {"written_at": datetime.now(UTC).isoformat()}
        col_doc = json_safe({
            **base, "provider": col.provider, "collection_short_name": col.collection_short_name,
            "version": col.version, "dataset_name": col.dataset_name, "product_type": col.product_type,
            "maturity": col.maturity, "concept_id": col.cmr_concept_id, "documentation_url": col.documentation_url,
        })
        doc = json_safe({
            **base, "provider": acq.provider, "granule_id": acq.granule_id, "collection": col.collection_short_name,
            "collection_version": col.version, "product_type": acq.product_type, "maturity": acq.maturity,
            "status": acq.status, "acquisition_start": acq.acquisition_start, "acquisition_end": acq.acquisition_end,
            "file_format": acq.file_format, "file_size_bytes": acq.file_size_bytes,
            "source_url": _strip_query(acq.download_url), "local_file_path": acq.local_file_path,
            "checksum": acq.checksum, "checksum_algorithm": acq.checksum_algorithm,
            "retrieved_at": acq.retrieved_at, "validation_report": acq.validation_report,
            "note": "File checks only; not a scientific validation.",
        })
        out = storage.metadata_dir(data_root, "acquisitions") / f"{storage.safe_name(acq.granule_id)}.json"
        cout = storage.metadata_dir(data_root, "collections") / f"{storage.safe_name(col.collection_short_name)}.json"
        for path, content in ((out, doc), (cout, col_doc)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        return out

    # ---- queries for the API -------------------------------------------------------
    def list_acquisitions(
        self, *, product_type: str | None = None, status: str | None = None, maturity: str | None = None,
        area: uuid.UUID | None = None, start: datetime | None = None, end: datetime | None = None,
        offset: int = 0, limit: int = 50,
    ) -> tuple[list[DataAcquisition], int]:
        conds = [c for c in (
            DataAcquisition.product_type == product_type if product_type else None,
            DataAcquisition.status == status if status else None,
            DataAcquisition.maturity == maturity if maturity else None,
            DataAcquisition.monitored_area_id == area if area else None,
            DataAcquisition.acquisition_start >= start if start else None,
            DataAcquisition.acquisition_start <= end if end else None,
        ) if c is not None]
        total = self.session.scalar(select(func.count()).select_from(DataAcquisition).where(*conds)) or 0
        rows = self.session.scalars(
            select(DataAcquisition).where(*conds)
            .order_by(DataAcquisition.acquisition_start.desc().nulls_last(), DataAcquisition.granule_id)
            .offset(offset).limit(limit)
        )
        return list(rows), total

    def list_jobs(self, *, status: str | None = None, offset: int = 0, limit: int = 50) -> tuple[list[DownloadJob], int]:
        conds = [DownloadJob.status == status] if status else []
        total = self.session.scalar(select(func.count()).select_from(DownloadJob).where(*conds)) or 0
        rows = self.session.scalars(
            select(DownloadJob).where(*conds).order_by(DownloadJob.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows), total
