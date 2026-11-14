"""Format-aware structural checks on downloaded files. NOT scientific validation; never raises on a bad file."""
from __future__ import annotations

import csv
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.services.data_acquisition.download_manager import hash_file, normalize_algorithm
from app.services.data_acquisition.types import CheckResult, GranuleRecord, ProviderName, ValidationReport

HGT_SIZES = {3601 * 3601 * 2: "1 arc-second", 1201 * 1201 * 2: "3 arc-second"}
HDF_EXT = {".h5", ".hdf5", ".nc", ".nc4"}
_ID_GROUP = "science/LSAR/identification"
_ID_KEYS = ("productType", "granuleId", "boundingPolygon", "zeroDopplerStartTime", "zeroDopplerEndTime")
DATE_TOLERANCE_S = 86400  # granule (catalog) vs file-embedded start time


def _text(v) -> str:
    v = v[()] if hasattr(v, "shape") and v.shape == () else v
    return (v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)).strip()


def _parse_dt(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=UTC)


class FileValidationService:
    def __init__(self, settings=None):
        self.settings = settings

    def validate(
        self,
        path: Path,
        granule: GranuleRecord,
        *,
        expected_checksum: str | None = None,
        expected_checksum_algorithm: str | None = None,
    ) -> ValidationReport:
        path = Path(path)
        rep = ValidationReport(ok=False)

        def add(name: str, passed: bool, detail: str = "") -> None:
            rep.checks.append(CheckResult(name, bool(passed), detail))

        exists = path.is_file()
        add("file_exists", exists, "" if exists else f"not a file: {path.name}")
        size = path.stat().st_size if exists else 0
        rep.size_bytes = size
        add("size_gt_zero", size > 0, f"{size} bytes")

        if exists:
            try:
                algo = normalize_algorithm(expected_checksum_algorithm) if expected_checksum else None
                digests = hash_file(path, "sha256", *([algo] if algo and algo != "sha256" else []))
                rep.sha256 = digests["sha256"]
                if expected_checksum and algo:
                    ok = digests[algo].lower() == expected_checksum.strip().lower()
                    add("checksum", ok, f"{algo} {'matches' if ok else 'MISMATCH'}")
                elif expected_checksum:
                    add("checksum", False, "expected checksum given without algorithm")
                else:
                    add("checksum", True, "sha256 computed; no expected checksum supplied")
            except Exception as e:  # noqa: BLE001 - validation must not raise
                add("checksum", False, f"could not read file: {e}")
        else:
            add("checksum", False, "file missing")

        fmt_ok, fmt_detail = False, "file missing or empty"
        if exists and size > 0:
            try:
                fmt_ok, fmt_detail = self._open(path, rep.extracted)
            except Exception as e:  # noqa: BLE001
                fmt_ok, fmt_detail = False, f"cannot open: {type(e).__name__}: {e}"
        add("format_opens", fmt_ok, fmt_detail)

        file_pt = rep.extracted.get("productType")
        if file_pt is None:
            add("product_type_matches", True, "not present in file")
        else:
            ok = file_pt.upper() == (granule.product_type or "").upper()
            add("product_type_matches", ok, f"file={file_pt} granule={granule.product_type}")

        add("dates_valid", *self._dates(granule, rep.extracted))
        add("footprint_valid", *self._footprint(granule))
        add("version_and_maturity_recorded", *self._version(granule, rep.extracted))

        rep.ok = all(c.passed for c in rep.checks)
        return rep

    # ---- format handlers ------------------------------------------------------
    def _open(self, path: Path, ex: dict) -> tuple[bool, str]:
        ext = path.suffix.lower()
        if ext in HDF_EXT:
            return self._hdf(path, ex)
        if ext in (".tif", ".tiff"):
            return self._tif(path, ex)
        if ext == ".hgt":
            n = path.stat().st_size
            return (n in HGT_SIZES, f"{n} bytes" + (f" = {HGT_SIZES[n]} tile" if n in HGT_SIZES else f"; expected one of {sorted(HGT_SIZES)}"))
        if ext == ".zip":
            return self._zip(path, ex)
        if ext == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as f:
                header = next(csv.reader(f), None)
            ex["columns"] = header or []
            return (bool(header and any(h.strip() for h in header)), f"{len(header or [])} columns")
        return False, f"unsupported file extension '{ext}'"

    def _hdf(self, path: Path, ex: dict) -> tuple[bool, str]:
        import h5py

        try:
            f = h5py.File(path, "r")
        except OSError as e:
            return False, f"not a readable HDF5/NetCDF4 file: {e}"
        with f:
            ex["top_level_groups"] = list(f.keys())
            if _ID_GROUP not in f:
                if path.suffix.lower() in (".h5", ".hdf5") and "science" in f:
                    return False, "NISAR-style file but /science/LSAR/identification is missing"
                return True, f"opened; groups: {', '.join(ex['top_level_groups']) or 'none'}"
            g = f[_ID_GROUP]
            for k in _ID_KEYS:
                if k in g:
                    ex[k] = _text(g[k])
            if "boundingPolygon" in ex:
                ex["bounding_polygon_wkt"] = ex["boundingPolygon"]
            return True, "opened; /science/LSAR/identification present"

    def _tif(self, path: Path, ex: dict) -> tuple[bool, str]:
        import rasterio

        with rasterio.open(path) as ds:
            ex.update(width=ds.width, height=ds.height, count=ds.count, crs=str(ds.crs) if ds.crs else None)
            if ds.width <= 0 or ds.height <= 0:
                return False, "zero raster dimension"
            if ds.crs is None:
                return False, "no CRS"
            return True, f"{ds.width}x{ds.height}, {ds.count} band(s), {ds.crs}"

    def _zip(self, path: Path, ex: dict) -> tuple[bool, str]:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                return False, f"corrupt entry: {bad}"
            infos = [i for i in z.infolist() if not i.is_dir()]
            if not infos:
                return False, "zip has no entries"
            ex["entries"] = [i.filename for i in infos]
            for i in infos:
                if i.filename.lower().endswith(".hgt") and i.file_size not in HGT_SIZES:
                    return False, f"{i.filename}: {i.file_size} bytes is not a valid .hgt size"
            return True, f"{len(infos)} entries"

    # ---- metadata checks ------------------------------------------------------
    def _dates(self, g: GranuleRecord, ex: dict) -> tuple[bool, str]:
        s, e = _aware(g.acquisition_start), _aware(g.acquisition_end)
        now = datetime.now(UTC)
        notes = []
        for label, d in (("start", s), ("end", e)):
            if d is None:
                continue
            if d.year < 1970:
                return False, f"{label} year {d.year} < 1970"
            if d > now:
                return False, f"{label} {d.isoformat()} is in the future"
        if s and e and s > e:
            return False, "acquisition_start is after acquisition_end"
        if s is None and e is None:
            notes.append("no granule dates")
        fs, fe = (_parse_dt(ex[k]) if k in ex else None for k in ("zeroDopplerStartTime", "zeroDopplerEndTime"))
        for k in ("zeroDopplerStartTime", "zeroDopplerEndTime"):
            if k in ex and _parse_dt(ex[k]) is None:
                return False, f"file {k} not parseable: {ex[k]!r}"
        if fs and fe and fs > fe:
            return False, "file zeroDopplerStartTime is after zeroDopplerEndTime"
        if fs and s and abs((fs - s).total_seconds()) > DATE_TOLERANCE_S:
            return False, f"file start {fs.isoformat()} differs from granule start {s.isoformat()}"
        return True, "; ".join(notes) or "ok"

    def _footprint(self, g: GranuleRecord) -> tuple[bool, str]:
        fp = g.footprint
        if fp is None:
            return True, "no footprint on granule"
        if fp.is_empty or not fp.is_valid:
            return False, "footprint empty or invalid geometry"
        minx, miny, maxx, maxy = fp.bounds
        if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
            return False, f"footprint outside lon/lat bounds: {fp.bounds}"
        return True, "ok"

    def _version(self, g: GranuleRecord, ex: dict) -> tuple[bool, str]:
        if not (g.version or "").strip():
            return False, "granule version is empty"
        ex["version"] = g.version
        if g.provider == ProviderName.NISAR:
            if g.maturity is None:
                return False, "NISAR granule has no maturity recorded"
            ex["maturity"] = str(g.maturity)
        return True, f"version={g.version} maturity={g.maturity}"
