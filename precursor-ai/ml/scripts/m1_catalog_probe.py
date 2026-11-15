"""M1 feasibility probe: anonymous, read-only catalog queries. NO login, NO file download.

Collection metadata goes through the Phase 2 seam (app.services.data_acquisition.cmr.find_collections,
imported read-only). Granule counts / first / last dates / sizes use the public CMR granule search
(metadata only; page_size<=20) because the Phase 2 seam returns lists, not hit counts.
Output: ml/reports/m1_probe/probe_results.json (real responses only; failures recorded, never filled).

Run from precursor-ai/:  backend/.venv/Scripts/python ml/scripts/m1_catalog_probe.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

CMR = "https://cmr.earthdata.nasa.gov/search"
OUT = ROOT / "ml" / "reports" / "m1_probe" / "probe_results.json"

# Candidate regions (bbox W,S,E,N). Illustrative candidates only, not a decision.
REGIONS = {
    "nepal_central": (83.0, 27.0, 86.5, 29.0),
    "italy_alps_apennine": (9.0, 43.5, 13.5, 46.5),
    "california_central_coast": (-123.0, 34.5, -119.5, 38.0),
    "oregon_washington": (-124.5, 44.0, -121.5, 47.5),
    "taiwan": (120.0, 22.0, 122.0, 25.5),
    "japan_kyushu": (129.5, 31.0, 132.0, 34.0),
    "colombia_andes": (-77.5, 4.0, -74.0, 7.5),
    "sabah_borneo": (115.0, 4.0, 118.5, 7.5),
    "caucasus_azerbaijan": (47.0, 40.5, 50.0, 42.0),
    "puerto_rico": (-67.5, 17.8, -65.2, 18.6),
}

NISAR = [f"NISAR_L2_{p}{m}_V1" for p in ("GUNW", "GCOV", "GSLC", "GOFF") for m in ("", "_PROVISIONAL", "_BETA")]
NISAR += ["NISAR_L3_SME2_PROVISIONAL_V1", "NISAR_L3_SME2_BETA_V1"]
OTHER = {  # short_name -> note
    "OPERA_L3_DISP-S1_V1": "OPERA displacement from Sentinel-1",
    "OPERA_L2_RTC-S1_V1": "OPERA Sentinel-1 RTC backscatter",
    "NASADEM_HGT": "DEM",
    "GPM_3IMERGDF": "IMERG daily final",
    "SPL3SMP_E": "SMAP enhanced L3 soil moisture",
    "SPL4SMGP": "SMAP L4 global 3-hourly 9 km soil moisture",
    "ALOS_PALSAR_RTC_HIGH_RES": "ALOS PALSAR RTC (ASF, 2006-2011)",
}


def get(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "precursor-ml-m1-probe"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.headers, json.loads(r.read())
        except Exception as exc:  # record, retry, then give up honestly
            err = f"{type(exc).__name__}: {exc}"
            time.sleep(2 * (attempt + 1))
    return None, {"error": err}


def granules(short_name, bbox=None, sort="start_date", n=1, extra=""):
    q = f"{CMR}/granules.json?short_name={urllib.parse.quote(short_name)}&page_size={n}&sort_key={sort}{extra}"
    if bbox:
        q += "&bounding_box=" + ",".join(str(v) for v in bbox)
    h, body = get(q)
    if h is None:
        return {"error": body["error"]}
    hits = int(h.get("CMR-Hits", -1))
    items = body.get("feed", {}).get("entry", [])
    return {
        "hits": hits,
        "items": [
            {"title": i.get("title"), "start": i.get("time_start"), "end": i.get("time_end"),
             "size_mb": float(i["granule_size"]) if i.get("granule_size") else None}
            for i in items
        ],
    }


def collection_meta(short_name):
    q = f"{CMR}/collections.json?short_name={urllib.parse.quote(short_name)}&page_size=5"
    h, body = get(q)
    if h is None:
        return {"error": body["error"]}
    out = []
    for e in body.get("feed", {}).get("entry", []):
        out.append({k: e.get(k) for k in ("id", "short_name", "version_id", "time_start", "time_end",
                                          "data_center", "processing_level_id", "title")})
    return out


def main() -> None:
    res: dict = {"run_utc": datetime.now(timezone.utc).isoformat(), "nisar": {}, "other": {}, "regions": {}}

    # Phase 2 seam check (read-only import): confirms the existing service sees NISAR GUNW.
    try:
        from app.services.data_acquisition import cmr as p2cmr
        found = p2cmr.find_collections(short_name="NISAR_L2_GUNW_V1")
        res["phase2_seam_find_collections_GUNW"] = len(found)
    except Exception as exc:
        res["phase2_seam_find_collections_GUNW"] = f"ERROR {type(exc).__name__}: {exc}"

    for sn in NISAR:
        d = {"collection": collection_meta(sn)}
        d["first"] = granules(sn, sort="start_date")
        d["last"] = granules(sn, sort="-start_date")
        d["sample_sizes"] = granules(sn, n=20, sort="-start_date")
        res["nisar"][sn] = d
        print("nisar", sn, d["first"].get("hits"), flush=True)

    for sn, note in OTHER.items():
        d = {"note": note, "collection": collection_meta(sn)}
        d["first"] = granules(sn, sort="start_date")
        d["last"] = granules(sn, sort="-start_date")
        res["other"][sn] = d
        print("other", sn, d["first"].get("hits"), flush=True)

    # Per-region counts (metadata only).
    for name, bb in REGIONS.items():
        r = {"bbox": bb}
        for sn in ("NISAR_L2_GUNW_V1", "NISAR_L2_GUNW_PROVISIONAL_V1", "NISAR_L2_GUNW_BETA_V1",
                   "NISAR_L2_GCOV_V1", "NISAR_L2_GSLC_V1", "OPERA_L3_DISP-S1_V1"):
            first = granules(sn, bb, sort="start_date")
            last = granules(sn, bb, sort="-start_date")
            r[sn] = {"hits": first.get("hits"), "first": (first.get("items") or [{}])[0].get("start"),
                     "last": (last.get("items") or [{}])[0].get("start"), "err": first.get("error")}
        res["regions"][name] = r
        print("region", name, r["NISAR_L2_GUNW_V1"]["hits"], flush=True)

    # Sentinel-1 via asf_search (search only; counts per region from 2014-10 on).
    try:
        import asf_search as asf
        s1 = {}
        for name, (w, s, e, n) in REGIONS.items():
            wkt = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
            hits = asf.search(platform=[asf.PLATFORM.SENTINEL1], processingLevel=["SLC"], intersectsWith=wkt,
                              start="2023-01-01", end="2023-12-31", maxResults=2000)
            s1[name] = {"slc_2023_granules": len(hits), "capped_at_2000": len(hits) >= 2000}
            print("s1", name, len(hits), flush=True)
        res["sentinel1_slc_2023_by_region"] = s1
    except Exception as exc:
        res["sentinel1_slc_2023_by_region"] = f"ERROR {type(exc).__name__}: {exc}"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
