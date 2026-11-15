"""M5b proposal probe: COUNT-ONLY and metadata queries against official landslide-inventory map services (no feature download, no login).
Output: ml/reports/m5b_probe/inventory_probe.json.  Run: python ml/scripts/m5b_inventory_probe.py  (standard library only)."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml/reports/m5b_probe/inventory_probe.json"
UA = {"User-Agent": "precursor-ml-proposal"}
W = {"OR_WA": (-124, 45, -121, 48), "CA_N": (-123, 37, -120, 40), "CA_S": (-119, 32, -116, 35)}


def g(u, t=45):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read())
    except Exception as e:  # recorded, never filled
        return {"error": f"{type(e).__name__}: {str(e)[:100]}"}


def layers(base):
    d = g(base + "?f=json")
    return [(l["id"], l["name"], l.get("subLayerIds"), l.get("geometryType")) for l in d.get("layers", [])], d.get("error"), (d.get("copyrightText") or "")[:300]


def count(base, lid, bb):
    q = urllib.parse.urlencode({"where": "1=1", "geometry": ",".join(map(str, bb)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "returnCountOnly": "true", "f": "json"})
    d = g(f"{base}/{lid}/query?{q}")
    return d.get("count", d.get("error"))


def fields(base, lid):
    d = g(f"{base}/{lid}?f=json")
    return {"name": d.get("name"), "geometry": d.get("geometryType"), "fields": [f["name"] for f in d.get("fields", []) or []], "error": d.get("error")}


def main():
    out = {}
    for s in ("LandslideInventory_DC1_Younger", "LandslideInventory_DC1_Older", "LandslideInventory_DC2", "LandslideInventory_DC3"):
        base = f"https://gis.conservation.ca.gov/server/rest/services/CGS/{s}/MapServer"
        ls, err, cr = layers(base)
        res = {name: {w: count(base, lid, bb) for w, bb in W.items() if w != "OR_WA"} for lid, name, sub, _ in ls if not sub}
        first = next((lid for lid, _, sub, _ in ls if not sub), None)
        out["CGS/" + s] = {"error": err, "copyright": cr, "counts": res, "sample_fields": fields(base, first) if first is not None else None}
        print(s, "done", flush=True)
    base = "https://gis.dogami.oregon.gov/arcgis/rest/services/Public/SLIDO42/MapServer"
    ls, err, cr = layers(base)
    out["DOGAMI/SLIDO42"] = {"error": err, "copyright": cr, "layers": {name: {"OR_WA": count(base, lid, W["OR_WA"]), "fields": fields(base, lid)["fields"][:40]} for lid, name, sub, _ in ls if not sub}}
    print("SLIDO done", flush=True)
    for svc in ("Public_Geology/Landslide_Inventory_Database/MapServer", "Hosted/Landslides_Offline/FeatureServer"):
        base = "https://gis.dnr.wa.gov/site1/rest/services/" + svc
        ls, err, cr = layers(base)
        out["WADNR/" + svc] = {"error": err, "copyright": cr, "n_layers": len(ls),
                               "layers": {f"{lid}:{name}": {"OR_WA": count(base, lid, W["OR_WA"])} for lid, name, sub, _ in ls[:40] if not sub}}
        first = next((lid for lid, _, sub, _ in ls if not sub), None)
        if first is not None:
            out["WADNR/" + svc]["sample_fields"] = fields(base, first)
        print(svc, "done", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
