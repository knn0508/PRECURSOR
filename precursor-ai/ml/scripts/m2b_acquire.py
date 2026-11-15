"""M2b / round 2 acquisition of the APPROVED list only (user, 2026-11-15): HydroRIVERS NA, USGS Qfaults, SoilGrids (5 properties x 3 depths,
mean), VIIRS VNP13A3 NDVI 2013-2017 (Option A). OSM roads were NOT approved. No new dependency; Phase 2 services read-only.

Sub-commands (run from precursor-ai/, one step at a time; every step stops on a deviation):
  ndvi-test   fetch ONE NDVI granule (safety step a); the caller then inspects it
  vectors     download HydroRIVERS + Qfaults (safety step b); the caller then opens them
  soil-plan   read the single SoilGrids VRT index, enumerate tiles for the 3 windows, check ALL 15 layer paths with HEAD
  soil        download the SoilGrids tiles
  ndvi        download the remaining NDVI granules
Manifest: data/ml/raw/manifest_round2.json (separate from the M2 manifest). Sizes may deviate at most 10% from the measured ones.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
RAW = ROOT / "data/ml/raw"
MAN = RAW / "manifest_round2.json"
PROBE = ROOT / "ml/reports/m2b_probe"
WINDOWS = {"OR_WA": (-124, 45, -121, 48), "CA_N": (-123, 37, -120, 40), "CA_S": (-119, 32, -116, 35)}
TOL = 0.10
LIMITS = {"total": 30e9, "file": 2e9, "free_min": 15e9}
HYDRO = ("https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_na_shp.zip", 66_335_898, "hydrorivers/HydroRIVERS_v10_na_shp.zip",
         "HydroSHEDS licence (free use with attribution) - taken from provider policy, text NOT_VERIFIED")
QFAULT = ("https://earthquake.usgs.gov/static/lfs/nshm/qfaults/Qfaults_GIS.zip", 32_371_696, "faults/Qfaults_GIS.zip",
          "U.S. Geological Survey, public domain - taken from provider policy, text NOT_VERIFIED")
SOIL_BASE = "https://files.isric.org/soilgrids/latest/data"
SOIL_PROPS = ["clay", "sand", "silt", "bdod", "cfvo"]
SOIL_DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]
SOIL_LICENCE = "CC BY 4.0 (ISRIC SoilGrids 2.0) - taken from provider policy/snippets, text NOT_VERIFIED"
SOIL_TILE_B = 406_513  # one tile measured by HEAD in the proposal
NDVI_LICENCE = "NASA open data (LP DAAC), no restrictions stated - taken from provider policy, text NOT_VERIFIED"
UA = {"User-Agent": "precursor-ml-m2b"}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_manifest():
    return json.loads(MAN.read_text()) if MAN.exists() else {}


def free_ok(extra):
    free = shutil.disk_usage(RAW).free
    return free - extra >= LIMITS["free_min"], free


def head(url):
    r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60)
    return int(r.headers["Content-Length"])


def record(manifest, key, dataset, url, licence, res, expected, extra=None):
    manifest[key] = {"dataset": dataset, "url": urlsplit(url)._replace(query="").geturl(), "licence": licence, "retrieved_utc": now(),
                     "size_bytes": res.size_bytes, "expected_size": expected, "sha256": res.sha256, **(extra or {})}
    MAN.write_text(json.dumps(manifest, indent=1))


def downloader():
    from app.core.config import get_settings
    from app.services.data_acquisition.download_manager import DownloadManager
    from app.services.data_acquisition.authentication import EarthdataAuthenticationService
    s = get_settings()
    return DownloadManager(s), EarthdataAuthenticationService(s)


def within(actual, expected):
    return abs(actual - expected) <= TOL * expected


# ------------------------------------------------------------------------------------------------------------- NDVI
def ndvi_catalog():
    """All VNP13A3 v002 granules 2013-01..2017-12 for the 4 tiles from the CMR catalog (metadata only)."""
    out = []
    for t in ("h09v04", "h08v04", "h08v05", "h07v05"):
        u = ("https://cmr.earthdata.nasa.gov/search/granules.json?short_name=VNP13A3&version=002&page_size=2000"
             "&temporal=2013-01-01T00:00:00Z,2017-12-31T23:59:59Z&options[readable_granule_name][pattern]=true"
             f"&readable_granule_name=*.{t}.*")
        d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90).read())
        for e in d["feed"]["entry"]:
            href = next(l["href"] for l in e["links"] if l.get("rel", "").endswith("/data#") and l["href"].endswith(".h5"))
            out.append({"tile": t, "id": e["title"], "url": href, "size_mib": float(e["granule_size"]), "start": e["time_start"]})
    return sorted(out, key=lambda x: (x["start"], x["tile"]))


def fetch_ndvi(items, label):
    dm, auth = downloader()
    sess = auth.get_session()
    man = load_manifest()
    tot = sum(i["size_mib"] for i in items) * 1048576
    ok, free = free_ok(tot)
    if not ok or tot > LIMITS["total"]:
        print("STOP: disk/total limits", free, tot)
        return 2
    for i in items:
        key = f"ndvi_viirs/{Path(urlsplit(i['url']).path).name}"
        dest = RAW / key
        if key in man and dest.exists() and dest.stat().st_size == man[key]["size_bytes"]:
            continue
        exp = int(i["size_mib"] * 1048576)  # CMR size is MiB with rounding: used only for the 10% check
        res = dm.download(i["url"], dest, session=sess)
        if not within(res.size_bytes, exp) or res.size_bytes > LIMITS["file"]:
            print("STOP: unexpected size", key, res.size_bytes, exp)
            return 2
        record(man, key, "VNP13A3_V002", i["url"], NDVI_LICENCE, res, exp, {"tile": i["tile"], "start": i["start"]})
        print("ok", key, res.size_bytes, flush=True)
    print(label, "done")
    return 0


def cmd_ndvi_test():
    cat = ndvi_catalog()
    PROBE.mkdir(parents=True, exist_ok=True)
    (PROBE / "ndvi_catalog.json").write_text(json.dumps(cat, indent=1))
    print("catalog granules", len(cat), "total MiB", round(sum(c["size_mib"] for c in cat), 1))
    test = next(c for c in cat if c["tile"] == "h08v05" and c["start"].startswith("2013-07"))
    return fetch_ndvi([test], "ndvi-test")


def cmd_ndvi():
    cat = json.loads((PROBE / "ndvi_catalog.json").read_text())
    return fetch_ndvi(cat, "ndvi")


# ------------------------------------------------------------------------------------------------------------- vectors
def cmd_vectors():
    dm, _ = downloader()
    import requests
    man = load_manifest()
    for url, exp, key, lic in (HYDRO, QFAULT):
        dest = RAW / key
        if key in man and dest.exists():
            continue
        res = dm.download(url, dest, session=requests.Session())
        if not within(res.size_bytes, exp):
            print("STOP: unexpected size", key, res.size_bytes, exp)
            return 2
        record(man, key, Path(key).stem, url, lic, res, exp)
        print("ok", key, res.size_bytes, flush=True)
    return 0


# ------------------------------------------------------------------------------------------------------------- soil
def vrt_index():
    """Tile geometry from the single clay_0-5cm_mean VRT (all layers share it)."""
    vrt = RAW / "soilgrids/_index/clay_0-5cm_mean.vrt"
    if not vrt.exists():
        dm, _ = downloader()
        import requests
        url = f"{SOIL_BASE}/clay/clay_0-5cm_mean.vrt"
        res = dm.download(url, vrt, session=requests.Session())
        if not within(res.size_bytes, 5_929_079):
            print("STOP: VRT size", res.size_bytes)
            sys.exit(2)
        man = load_manifest()
        record(man, "soilgrids/_index/clay_0-5cm_mean.vrt", "SOILGRIDS_VRT_INDEX", url, SOIL_LICENCE, res, 5_929_079)
    root = ET.parse(vrt).getroot()
    gt = [float(x) for x in root.find("GeoTransform").text.split(",")]
    tiles = []
    for src in root.iter("ComplexSource"):
        fn = src.find("SourceFilename").text
        d = src.find("DstRect")
        tiles.append({"rel": fn.replace("./clay_0-5cm_mean/", ""), "x": float(d.get("xOff")), "y": float(d.get("yOff")), "w": float(d.get("xSize")), "h": float(d.get("ySize"))})
    return gt, int(root.get("rasterXSize")), int(root.get("rasterYSize")), tiles


def window_tiles():
    import numpy as np
    from pyproj import Transformer
    gt, W, H, tiles = vrt_index()
    t = Transformer.from_crs(4326, "+proj=igh +ellps=WGS84 +units=m +no_defs", always_xy=True)
    sel = {}
    for name, (w, s, e, n) in WINDOWS.items():
        lon = np.concatenate([np.linspace(w, e, 80), np.full(80, e), np.linspace(e, w, 80), np.full(80, w)])
        lat = np.concatenate([np.full(80, s), np.linspace(s, n, 80), np.full(80, n), np.linspace(n, s, 80)])
        x, y = t.transform(lon, lat)
        px, py = (x - gt[0]) / gt[1], (y - gt[3]) / gt[5]
        pad = 2  # a couple of pixels so edge cells have data on both sides
        for tl in tiles:
            if tl["x"] <= px.max() + pad and tl["x"] + tl["w"] >= px.min() - pad and tl["y"] <= py.max() + pad and tl["y"] + tl["h"] >= py.min() - pad:
                sel.setdefault(tl["rel"], tl)
                sel[tl["rel"]].setdefault("windows", []).append(name)
    return gt, W, H, list(sel.values())


def cmd_soil_plan():
    """HEAD every tile of every approved layer. A layer with ANY missing tile is a path mismatch: it is excluded from the plan and
    reported (the user decides); complete layers are planned with their HEAD-measured sizes."""
    import concurrent.futures as cf
    import urllib.error
    gt, W, H, tiles = window_tiles()
    PROBE.mkdir(parents=True, exist_ok=True)
    layers = [(p, d) for p in SOIL_PROPS for d in SOIL_DEPTHS]

    def chk(a):
        (p, d), t = a
        u = f"{SOIL_BASE}/{p}/{p}_{d}_mean/{t['rel']}"
        try:
            return (p, d, t, u, 200, head(u))
        except urllib.error.HTTPError as e:
            return (p, d, t, u, e.code, 0)

    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(chk, [(l, t) for l in layers for t in tiles]))
    bad = {}
    for p, d, t, u, st, sz in res:
        if st != 200:
            bad.setdefault(f"{p}_{d}", []).append(t["rel"])
    print("tiles per layer", len(tiles), "layers", len(layers), "layers with missing tiles:", {k: len(v) for k, v in bad.items()})
    plan = [{"layer": f"{p}_{d}", "prop": p, "depth": d, "rel": t["rel"], "url": u, "size": sz, "x": t["x"], "y": t["y"], "w": t["w"], "h": t["h"],
             "windows": t["windows"]} for p, d, t, u, st, sz in res if st == 200 and f"{p}_{d}" not in bad]
    (PROBE / "soil_plan.json").write_text(json.dumps({"geotransform": gt, "vrt_size": [W, H], "tiles": tiles, "files": plan, "excluded_layers_missing_tiles": bad}, indent=1))
    print("planned files", len(plan), "bytes", sum(f["size"] for f in plan))
    return 2 if bad else 0


def cmd_soil():
    plan = json.loads((PROBE / "soil_plan.json").read_text())
    files = plan["files"]
    est = sum(f["size"] for f in files)
    ok, free = free_ok(est)
    if not ok or est > 0.35e9:
        print("STOP: planned soil size", est, "disk free", free)
        return 2
    dm, _ = downloader()
    import requests
    man = load_manifest()
    sess = requests.Session()
    n = 0
    for f in files:
        key = f"soilgrids/{f['prop']}/{f['depth']}/{Path(f['rel']).name.replace('.tif', '')}__{f['layer']}.tif"
        dest = RAW / key
        if key in man and dest.exists():
            continue
        res = dm.download(f["url"], dest, session=sess)
        if not within(res.size_bytes, f["size"]) or res.size_bytes > LIMITS["file"]:
            print("STOP: unexpected tile size", key, res.size_bytes)
            return 2
        record(man, key, "SOILGRIDS_2_0", f["url"], SOIL_LICENCE, res, f["size"], {"layer": f["layer"], "rel": f["rel"], "vrt_x": f["x"], "vrt_y": f["y"]})
        n += 1
    print("soil done; new files", n, "total tiles", len(files))
    return 0


if __name__ == "__main__":
    cmds = {"ndvi-test": cmd_ndvi_test, "vectors": cmd_vectors, "soil-plan": cmd_soil_plan, "soil": cmd_soil, "ndvi": cmd_ndvi}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(2)
    sys.exit(cmds[sys.argv[1]]())
