"""M1: catalog coverage of census candidate windows (anonymous metadata queries only). Output: ml/reports/m1_probe/candidate_coverage.json
Run from precursor-ai/: ml/.venv/Scripts/python ml/scripts/m1_candidate_coverage.py   (needs asf_search: use backend/.venv)"""
import json, math, urllib.parse, urllib.request
from pathlib import Path
import asf_search as asf
ROOT = Path(__file__).resolve().parents[2]
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
WIN = {
 "mexico_oaxaca_coolr": (-97, 15, -94, 18), "philippines_luzon_coolr": (119, 16, 122, 19), "vietnam_north_coolr": (102, 21, 105, 24),
 "california_north_glc": (-123, 37, -120, 40), "oregon_washington_glc": (-124, 45, -121, 48), "california_south_glc": (-119, 32, -116, 35),
 "nepal_reference": (83, 27, 86, 30),
}
def hits(sn, bb, extra=""):
    q = f"{CMR}?short_name={sn}&page_size=1&bounding_box={','.join(map(str,bb))}{extra}"
    r = urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "precursor-ml-m1"}), timeout=60)
    return int(r.headers["CMR-Hits"])
out = {}
for n, (w, s, e, nn) in WIN.items():
    wkt = f"POLYGON(({w} {s},{e} {s},{e} {nn},{w} {nn},{w} {s}))"
    s1 = {}
    for y in (2015, 2017, 2022, 2023):
        s1[y] = len(asf.search(platform=[asf.PLATFORM.SENTINEL1], processingLevel=["SLC"], intersectsWith=wkt,
                               start=f"{y}-01-01", end=f"{y}-12-31", maxResults=1500))
    out[n] = {"bbox": (w, s, e, nn), "nasadem_tiles": (math.ceil(e) - math.floor(w)) * (math.ceil(nn) - math.floor(s)),
              "s1_slc_granules_per_year": s1, "opera_disp_granules": hits("OPERA_L3_DISP-S1_V1", (w, s, e, nn)),
              "nisar_gunw_provisional": hits("NISAR_L2_GUNW_PROVISIONAL_V1", (w, s, e, nn))}
    print(n, out[n], flush=True)
(ROOT / "ml/reports/m1_probe/candidate_coverage.json").write_text(json.dumps(out, indent=1))
