"""M2: integrity verification of downloaded files (integrity ONLY; not scientific validation).
Recomputes SHA-256 against data/ml/raw/manifest.json, tests zips, opens GeoTIFFs with rasterio.
Output: data/ml/raw/integrity.json.  Run: ml/.venv/Scripts/python ml/scripts/m2_verify.py (from precursor-ai/)"""
import hashlib, json, zipfile
from pathlib import Path
import rasterio
ROOT = Path(__file__).resolve().parents[2]; RAW = ROOT / "data/ml/raw"
man = json.loads((RAW / "manifest.json").read_text()); out = {}
for key, m in man.items():
    p = RAW / key; r = {"exists": p.exists()}
    if p.exists():
        h = hashlib.sha256()
        with p.open("rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
        r["size_ok"] = p.stat().st_size == m["size_bytes"]; r["sha256_ok"] = h.hexdigest() == m["sha256"]
        try:
            if p.suffix == ".zip":
                z = zipfile.ZipFile(p); r["zip_testzip"] = z.testzip() is None; r["members"] = z.namelist()[:3]
                if key.startswith("geology_state/"):
                    import pyogrio
                    shp = [n for n in z.namelist() if n.lower().endswith(".shp")][0]
                    info = pyogrio.read_info(f"/vsizip/{p.as_posix()}/{shp}")
                    r.update(shp=shp, features=int(info["features"]), crs=str(info["crs"])[:40], fields=len(info["fields"]))
                    r["read_ok"] = info["features"] > 0
            elif p.suffix == ".HDF5":
                with p.open("rb") as fh:
                    r["hdf5_signature_ok"] = fh.read(8) == bytes.fromhex("894844460d0a1a0a")
                try:  # h5py exists only in the backend venv; the signature check above always runs
                    import h5py
                    with h5py.File(p, "r") as h:
                        r["h5_has_precipitation"] = "Grid/precipitation" in h
                except ImportError:
                    pass
                r["read_ok"] = r["hdf5_signature_ok"]
            elif p.suffix == ".tif":
                with rasterio.open(p) as d:
                    r.update(crs=str(d.crs), width=d.width, height=d.height, count=d.count, dtype=d.dtypes[0],
                             bounds=[round(v, 4) for v in d.bounds], nodata=d.nodata)
                    r["read_ok"] = d.read(1, window=((0, 64), (0, 64))).size == 4096
        except Exception as e:
            r["error"] = type(e).__name__
    out[key] = r
(RAW / "integrity.json").write_text(json.dumps(out, indent=1))
bad = {k: v for k, v in out.items() if not (v.get("exists") and v.get("size_ok") and v.get("sha256_ok") and not v.get("error") and v.get("zip_testzip", True) and v.get("read_ok", True))}
print(len(out), "files;", len(bad), "failing integrity", list(bad)[:5])
