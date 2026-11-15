"""M2 acquisition of the APPROVED list only (ML track). Reuses Phase 2 services read-only; no database.

Approved (user, 2026-11-15): NASADEM tiles for 3 windows, ESA WorldCover tiles, IMERG monthly (restricted to the years
covered by usable events, stop if > 5 GB (extended)), USGS SGMC (size-check first; NOT handled here: unmeasurable -> user decision).
Modes:  --plan      catalog/HEAD queries only; prints and writes the plan; downloads nothing
        --download  executes the plan (resumable, retries, disk checks, SHA-256, manifest). Idempotent.
Run from precursor-ai/ (the .env is read by Phase 2 Settings; credentials are never printed):
        backend/.venv/Scripts/python ml/scripts/m2_acquire.py --plan|--download
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

RAW = ROOT / "data/ml/raw"
MANIFEST = RAW / "manifest.json"
PLAN = ROOT / "ml/reports/m2_probe/m2_plan.json"

WINDOWS = {"OR_WA": (-124, 45, -121, 48), "CA_N": (-123, 37, -120, 40), "CA_S": (-119, 32, -116, 35)}
WORLDCOVER_TILES = ["N45W126", "N45W123", "N36W123", "N39W123", "N30W120", "N30W117", "N33W120", "N33W117"]
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
IMERG_RANGE = ("2001-06-01", "2017-12-31")  # user-approved 2026-11-15 (extended climatology; first catalog month verified at plan time)
LIMITS = {"total_bytes": 30 * 10**9, "file_bytes": 2 * 10**9, "min_free_bytes": 15 * 10**9, "imerg_stop_bytes": 5 * 10**9}
GEO_URL = "https://mrdata.usgs.gov/geology/state/shp/{s}.zip"  # per-state geologic map (USGS mrdata); user-approved substitute for SGMC (2026-11-15)
GEO_STATES = ["CA", "OR", "WA"]
LICENCE = {"USGS_STATE_GEOLOGY": "USGS public-domain data per USGS copyright policy; licence text on the page NOT_VERIFIED",
           "NASADEM": "NASA open data (LP DAAC), no use restrictions stated in catalog; NOT_VERIFIED text",
           "IMERG": "NASA open data (GES DISC); NOT_VERIFIED text",
           "WORLDCOVER": "CC BY 4.0 (ESA WorldCover 2021 v200)"}


def build_plan() -> list[dict]:
    from shapely.geometry import box
    from app.services.data_acquisition import cmr
    from app.services.data_acquisition.aoi import AOI
    from app.services.data_acquisition.providers._cmr_common import file_info, https_data_url
    from app.services.data_acquisition.providers.nasadem import tiles_for_aoi

    items: list[dict] = []
    # NASADEM: only tiles whose interior overlaps each window (Phase 2 tiles_for_aoi)
    seen: set[str] = set()
    for name, bb in WINDOWS.items():
        aoi = AOI.from_geometry(name, box(*bb))
        want = set(tiles_for_aoi(aoi)) - seen
        got = cmr.find_granules("NASADEM_HGT", aoi=aoi, limit=100)
        for g in got:
            umm = g["umm"]
            ur = umm.get("GranuleUR", "").lower()
            tile = next((t for t in want if t in ur), None)
            if not tile:
                continue
            fi = file_info(umm)
            items.append({"dataset": "NASADEM_HGT_001", "window": name, "id": tile, "url": https_data_url(umm),
                          "auth": "earthdata", "expected_size": fi.get("size"), "size_exact": fi.get("size_exact"),
                          "published_checksum": fi.get("checksum"), "published_checksum_algorithm": fi.get("checksum_algorithm"),
                          "dest": f"nasadem/{Path(urlsplit(https_data_url(umm)).path).name}", "licence": LICENCE["NASADEM"]})
            seen.add(tile)
        missing = want - {i["id"] for i in items if i["dataset"] == "NASADEM_HGT_001"}
        if missing:
            items.append({"dataset": "NASADEM_HGT_001", "window": name, "id": ",".join(sorted(missing)),
                          "status": "NOT_IN_CATALOG"})
    # WorldCover: public bucket, HEAD for size
    for t in WORLDCOVER_TILES:
        url = WC_URL.format(t=t)
        r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "precursor-ml-m2"}), timeout=60)
        items.append({"dataset": "WORLDCOVER_2021_V200", "window": "B1", "id": t, "url": url, "auth": "none",
                      "expected_size": int(r.headers["Content-Length"]), "size_exact": True,
                      "dest": f"worldcover/{Path(urlsplit(url).path).name}", "licence": LICENCE["WORLDCOVER"]})
    # USGS per-state geologic maps (public host, HEAD for size)
    for st in GEO_STATES:
        url = GEO_URL.format(s=st)
        r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "precursor-ml-m2"}), timeout=60)
        items.append({"dataset": "USGS_STATE_GEOLOGY", "window": st, "id": st, "url": url, "auth": "none",
                      "expected_size": int(r.headers["Content-Length"]), "size_exact": True,
                      "dest": f"geology_state/{st}.zip", "licence": LICENCE["USGS_STATE_GEOLOGY"]})
    # IMERG monthly Final V07 over the approved climatology range
    lo, hi = (datetime.fromisoformat(x) for x in IMERG_RANGE)
    got = cmr.find_granules("GPM_3IMERGM", version="07", start=lo, end=hi.replace(hour=23, minute=59), limit=300)
    for g in got:
        umm = g["umm"]
        fi = file_info(umm)
        url = https_data_url(umm)
        items.append({"dataset": "GPM_3IMERGM_V07", "window": "B1", "id": umm.get("GranuleUR"), "url": url, "auth": "earthdata",
                      "expected_size": fi.get("size"), "size_exact": fi.get("size_exact"),
                      "published_checksum": fi.get("checksum"), "published_checksum_algorithm": fi.get("checksum_algorithm"),
                      "dest": f"imerg_monthly/{Path(urlsplit(url).path).name}", "licence": LICENCE["IMERG"]})
    return items


def summarize(items: list[dict]) -> dict:
    out = {}
    for it in items:
        d = out.setdefault(it["dataset"], {"files": 0, "bytes": 0, "unknown_size": 0, "not_in_catalog": 0})
        if it.get("status") == "NOT_IN_CATALOG":
            d["not_in_catalog"] += 1
            continue
        d["files"] += 1
        if it.get("expected_size"):
            d["bytes"] += it["expected_size"]
        else:
            d["unknown_size"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--skip", default="", help="comma list of dataset names to leave out of this run")
    a = ap.parse_args()
    if a.plan == a.download:
        ap.error("choose exactly one of --plan / --download")
    items = [i for i in build_plan() if i["dataset"] not in set(filter(None, a.skip.split(",")))]
    summ = summarize(items)
    total = sum(v["bytes"] for v in summ.values())
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps({"built_utc": datetime.now(timezone.utc).isoformat(), "limits": LIMITS, "summary": summ,
                                "total_bytes": total, "items": items}, indent=1))
    print(json.dumps(summ, indent=1), "total_bytes", total)
    big = [i for i in items if (i.get("expected_size") or 0) > LIMITS["file_bytes"]]
    unk = [i for i in items if not i.get("expected_size") and i.get("status") != "NOT_IN_CATALOG"]
    if big or unk or total > LIMITS["total_bytes"]:
        print("STOP: file over 2 GB / unknown size / total over limit", len(big), len(unk))
        return 2
    imerg = summ.get("GPM_3IMERGM_V07", {}).get("bytes", 0)
    if imerg > LIMITS["imerg_stop_bytes"]:
        print("STOP: IMERG total exceeds 5 GB:", imerg)
        return 2
    free = shutil.disk_usage(RAW.parent).free
    print("free disk", free, "needed", total, "after", free - total)
    if free - total < LIMITS["min_free_bytes"]:
        print("STOP: less than 15 GB would remain free")
        return 2
    if a.plan:
        return 0
    return download(items)


def download(items: list[dict]) -> int:
    from app.core.config import get_settings
    from app.services.data_acquisition.authentication import EarthdataAuthenticationService
    from app.services.data_acquisition.download_manager import DownloadManager, hash_file
    import requests

    settings = get_settings()
    dm = DownloadManager(settings)
    auth = EarthdataAuthenticationService(settings)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    edl = None
    failures = 0
    for it in items:
        if it.get("status") == "NOT_IN_CATALOG":
            continue
        dest = RAW / it["dest"]
        key = it["dest"]
        prev = manifest.get(key)
        if dest.exists() and prev and dest.stat().st_size == prev["size_bytes"]:
            if hash_file(dest, "sha256")["sha256"] == prev["sha256"]:
                continue  # idempotent: verified earlier
        try:
            if it["auth"] == "earthdata":
                edl = edl or auth.get_session()
                sess = edl
            else:
                sess = requests.Session()
            if free_after(it) < LIMITS["min_free_bytes"]:
                print("STOP: free disk would fall below 15 GB"); return 2
            res = dm.download(it["url"], dest, expected_size=it["expected_size"] if it.get("size_exact") else None,
                              checksum=it.get("published_checksum"), checksum_algorithm=it.get("published_checksum_algorithm"),
                              session=sess)
            growth = res.size_bytes - it["expected_size"] if it.get("expected_size") else 0
            if growth and abs(growth) > max(1024, 0.01 * it["expected_size"]):
                print("STOP: unexpected size", key, it["expected_size"], res.size_bytes); return 2
            manifest[key] = {"dataset": it["dataset"], "window": it["window"], "id": it["id"],
                             "url": urlsplit(it["url"])._replace(query="").geturl(), "licence": it["licence"],
                             "retrieved_utc": datetime.now(timezone.utc).isoformat(), "size_bytes": res.size_bytes,
                             "expected_size": it["expected_size"], "sha256": res.sha256,
                             "published_checksum": it.get("published_checksum")}
            MANIFEST.write_text(json.dumps(manifest, indent=1))
            print("ok", key, res.size_bytes, flush=True)
        except Exception as exc:  # type name only; never echo anything credential-bearing
            failures += 1
            print("FAILED", key, type(exc).__name__, str(exc)[:160].replace("\n", " "), flush=True)
            if type(exc).__name__ == "AuthenticationError":
                return 3
    print("done; failures:", failures)
    return 1 if failures else 0


def free_after(it: dict) -> int:
    return shutil.disk_usage(RAW).free - (it.get("expected_size") or 0)


if __name__ == "__main__":
    sys.exit(main())
