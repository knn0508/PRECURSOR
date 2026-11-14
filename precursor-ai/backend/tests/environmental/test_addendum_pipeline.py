"""Phase 4 addendum integration: stack manifest, reference grid, SMAP, lithology, NDVI, distances, clipped soil/land-cover
rasters, IMERG half-hourly. EVERYTHING here is SYNTHETIC and labelled; passing proves wiring and honesty rules, not real-data validity."""
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
import rasterio
from geoalchemy2.shape import from_shape
from shapely.geometry import box
from sqlalchemy import select

from app.models import DataAcquisition, DataCollection, EnvironmentalLayer
from app.services.environmental import external_synthetic as xs
from app.services.environmental import storage, synthetic_raster as sr
from app.services.environmental.providers import synthetic as ps
from app.services.environmental.rainfall.synthetic_half_hourly import write_synthetic_half_hour
from app.services.environmental.smap.synthetic import write_synthetic_smap
from app.services.environmental.types import TEMPORAL_OF, LayerKind
from tests.environmental.test_pipeline_api import BASE, env, make_area, process, seed_dem, stages  # noqa: F401

SERIES_AREA = box(116.51, 5.01, 116.59, 5.09)  # inside the default synthetic IMERG/SMAP grids and the soil/land-cover rasters


def manifest(env, area):
    r = env.client.get(f"{BASE}/areas/{area.id}/manifest")
    assert r.status_code == 200, r.text
    return r.json()


def names(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k).lower()
            yield from names(v)
    elif isinstance(o, list):
        for v in o:
            yield from names(v)


def seed_dem_at(env, lon0, lat0, shape=(40, 40)):
    rel = f"raw/nasadem/{uuid.uuid4().hex[:6]}__NASADEM_synthetic.tif"
    f = env.root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    sr.make_plane_geographic(f, lat0=lat0, lon0=lon0, shape=shape)
    h, w = shape
    fp = box(lon0, lat0 - h / 3600, lon0 + w / 3600, lat0)
    col = DataCollection(provider="NASADEM", collection_short_name=f"N_{uuid.uuid4().hex[:5]}", dataset_name="x", product_type="DEM", version="1")
    env.db.add(col)
    env.db.flush()
    env.db.add(DataAcquisition(collection_id=col.id, provider="NASADEM", granule_id=f"D-{uuid.uuid4().hex[:5]}", product_type="DEM", status="VALIDATED",
                               local_file_path=rel, spatial_footprint=from_shape(fp, srid=4326)))
    env.db.commit()


def grid_of(env, rid):
    run = env.client.get(f"{BASE}/processing-runs/{rid}").json()
    return run


def run_grid(env, area):
    rid = process(env, area)
    m = manifest(env, area)
    return rid, m["reference_grid"], m


# --- manifest -------------------------------------------------------------------------------------------
def test_manifest_lists_every_kind_before_any_run(env):
    a = make_area(env)
    m = manifest(env, a)
    assert {e["layer_type"] for e in m["entries"]} == {k.value for k in LayerKind}
    assert m["counts"]["entries"] == len(LayerKind) and m["counts"]["available"] == 0 and m["reference_grid"] is None
    assert all(e["status"] == "NOT_RUN" and e["reason"] and e["lineage_hash"] is None and e["file"] is None for e in m["entries"])
    for e in m["entries"]:
        assert e["temporal_kind"] == TEMPORAL_OF[LayerKind(e["layer_type"])].value
    kinds = {e["layer_type"]: e["kind"] for e in m["entries"]}
    assert kinds["RAINFALL"] == kinds["SMAP_SOIL_MOISTURE"] == "series" and kinds["SEISMIC"] == kinds["HISTORICAL_LANDSLIDES"] == "vector"
    assert kinds["ELEVATION"] == kinds["LITHOLOGY"] == kinds["DISTANCE_RIVER"] == "raster"
    assert m["real_data_validation"] == "NOT_PERFORMED" and m["validation_status"] == "NOT_VALIDATED"
    assert env.client.get(f"{BASE}/areas/{uuid.uuid4()}/manifest").status_code == 404


def test_manifest_after_run_has_grid_aligned_rasters_and_file_json(env):
    a = make_area(env)
    seed_dem(env)
    rid, grid, m = run_grid(env, a)
    assert grid["crs"] == "EPSG:32650" and grid["epsg"] == 32650 and grid["resolution"] == {"x": 30.0, "y": 30.0, "unit": "metre"}
    assert grid["chosen_by"] == "auto" and grid["width"] >= 1 and len(grid["bounds"]) == 4 and len(grid["transform"]) == 6
    e = {x["layer_type"]: x for x in m["entries"]}
    for k in ("ELEVATION", "SLOPE", "ASPECT"):
        assert e[k]["status"] == "PROCESSED" and e[k]["on_reference_grid"] and e[k]["file"].endswith(".tif") and "/" not in e[k]["file"]
        assert e[k]["lineage_hash"] and len(e[k]["lineage_hash"]) == 64 and e[k]["synthetic"] is True and e[k]["temporal_kind"] == "static"
        assert e[k]["processing_resolution"]["unit"] == "metre" and e[k]["native_resolution"]["unit"] == "degree"
        assert e[k]["coverage"]["valid_percent"] is not None
    assert e["ELEVATION"]["source"]["provider"] == "NASADEM" and e["ELEVATION"]["units"] == "metre"
    assert e["RAINFALL"]["status"] in ("NOT_AVAILABLE", "NOT_RUN") and e["RAINFALL"]["reason"]
    assert m["counts"]["on_reference_grid"] == 3 and m["counts"]["synthetic"] >= 3 and m["contains_synthetic_data"] is True
    # aligned copy really is on the manifest grid
    lay = env.db.scalars(select(EnvironmentalLayer).where(EnvironmentalLayer.layer_type == "SLOPE")).first()
    with rasterio.open(storage.resolve_output(env.root, lay.aligned_file_path)) as s:
        assert s.crs.to_string() == "EPSG:32650" and (s.width, s.height) == (grid["width"], grid["height"])
        assert tuple(s.transform)[:6] == pytest.approx(tuple(grid["transform"]))
    # the file written by the MANIFEST stage matches the endpoint
    f = env.root / "processed/environmental" / str(a.id) / "features" / "manifest.json"
    assert f.is_file() and json.loads(f.read_text())["counts"]["entries"] == m["counts"]["entries"]
    text = json.dumps(m)
    assert str(env.root) not in text and str(env.root).replace("\\", "/") not in text
    assert not any(b in n for n in names(m) for b in ("risk", "probability", "susceptibility", "prediction", "score", "forecast"))
    _, st = stages(env, rid)
    assert st["REFERENCE_GRID"] == "DONE" and st["MANIFEST"] == "DONE"
    layers = {l["layer_type"]: l for l in env.client.get(f"{BASE}/areas/{a.id}/layers").json()["items"]}
    assert layers["ELEVATION"]["temporal_kind"] == "static" and layers["ELEVATION"]["aligned"] is True


# --- reference grid ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("lon0,lat0,epsg", [(116.0, 5.2, 32650), (-75.0, 40.2, 32618), (151.0, -33.8, 32756)])
def test_grid_crs_follows_the_aoi_not_a_constant(env, lon0, lat0, epsg):
    area = box(lon0 + 0.001, lat0 - 0.009, lon0 + 0.010, lat0 - 0.001)
    a = make_area(env, area, name=f"zone-{epsg}")
    seed_dem_at(env, lon0, lat0)
    rid, grid, m = run_grid(env, a)
    assert grid["epsg"] == epsg
    e = {x["layer_type"]: x for x in m["entries"]}
    assert e["SLOPE"]["on_reference_grid"] and e["SLOPE"]["crs"] is not None
    w, h = grid["width"], grid["height"]
    assert w * 30.0 >= 150 and h * 30.0 >= 150  # a ~0.009 degree AOI is a few hundred metres across


def test_aoi_straddling_a_utm_zone_boundary_warns_and_keeps_one_zone(env):
    a = make_area(env, box(5.995, 45.191, 6.005, 45.199), name="straddle")
    seed_dem_at(env, 5.99, 45.2, shape=(40, 80))
    rid, grid, _ = run_grid(env, a)
    assert grid["epsg"] == 32632 and any("zone" in w.lower() for w in grid["warnings"])
    _, st = stages(env, rid)
    assert st["REFERENCE_GRID"] == "DONE"


def test_aoi_smaller_than_a_raster_cell_still_gets_a_grid(env):
    a = make_area(env, box(116.0050, 5.1950, 116.00502, 5.19502), name="tiny")  # ~2 m: far below the 30 m cell and the DEM cell
    seed_dem(env)
    rid, grid, m = run_grid(env, a)
    assert grid["width"] >= 1 and grid["height"] >= 1
    run = env.client.get(f"{BASE}/processing-runs/{rid}").json()
    assert run["status"] in ("COMPLETED", "PARTIAL", "FAILED")  # never a crash/500
    assert not any(b in n for n in names(m) for b in ("risk", "probability", "score"))


def test_user_crs_and_resolution_are_honoured_and_invalid_crs_is_reported(env):
    a = make_area(env)
    seed_dem(env)
    rid = process(env, a, grid_crs="EPSG:32649", grid_resolution_m=60)
    g = manifest(env, a)["reference_grid"]
    assert g["epsg"] == 32649 and g["chosen_by"] == "user" and g["resolution"]["x"] == 60.0
    b = make_area(env, name="geographic")
    rid2 = process(env, b, grid_crs="EPSG:4326")
    run, st = stages(env, rid2)
    assert st["REFERENCE_GRID"] == "FAILED" and run["status"] in ("PARTIAL", "FAILED")  # geographic CRS is refused, stage isolated
    assert env.client.post(f"{BASE}/areas/{a.id}/process", json={"grid_crs": "not-a-crs"}).status_code == 422
    assert env.client.post(f"{BASE}/areas/{a.id}/process", json={"grid_resolution_m": 0}).status_code == 422
    assert env.client.post(f"{BASE}/areas/{a.id}/process", json={"rainfall_resolution": "hourly"}).status_code == 422


# --- new stages ---------------------------------------------------------------------------------------------
def place_external(env):
    root = env.root
    xs.make_lithology_raster(storage.external_dir(root, "lithology"), (116.5, 5.0, 116.6, 5.1), "EPSG:4326", shape=(30, 30))  # mixed CRS vs the UTM grid
    xs.make_ndvi_raster(storage.external_dir(root, "ndvi"), (116.5, 5.0, 116.6, 5.1), "EPSG:4326", shape=(30, 30))
    for kind, sub in (("river", "rivers"), ("fault", "faults")):  # no roads on purpose
        xs.make_vector_geojson(storage.external_dir(root, sub), kind, (116.4, 4.9, 116.7, 5.2))
    sd = storage.external_dir(root, "soilgrids")
    sd.mkdir(parents=True, exist_ok=True)
    ps.write_synthetic_soil(sd, "clay", 0, 5, "mean", np.full((10, 10), 300, dtype="int16"), west=116.0, north=5.2, pixel=0.1)
    ld = storage.external_dir(root, "land_cover")
    ld.mkdir(parents=True, exist_ok=True)
    ps.write_synthetic_land_cover(ld / "ESA_WorldCover_synthetic.tif", np.array([[10] * 5 + [40] * 5] * 10, dtype="uint8"), west=116.0, north=5.2, pixel=0.1)


def seed_series(env, hh_days=2):
    col = DataCollection(provider="SMAP", collection_short_name=f"SMAP_{uuid.uuid4().hex[:4]}", dataset_name="s", product_type="SMAP", version="1")
    hcol = DataCollection(provider="GPM", collection_short_name="GPM_3IMERGHH_synth", dataset_name="hh", product_type="IMERG", version="1")
    env.db.add_all([col, hcol])
    env.db.flush()
    for i in range(5):
        if i == 2:
            continue
        d = date(2024, 2, 1) + timedelta(days=i)
        rel = f"raw/smap/{d:%Y%m%d}__synthetic.h5"
        (env.root / rel).parent.mkdir(parents=True, exist_ok=True)
        write_synthetic_smap(env.root / rel, d)
        env.db.add(DataAcquisition(collection_id=col.id, provider="SMAP", granule_id=f"S-{d:%Y%m%d}", product_type="SMAP", status="VALIDATED",
                                   local_file_path=rel, acquisition_start=datetime.combine(d, datetime.min.time(), UTC)))
    for day in range(hh_days):
        d = date(2024, 3, 1) + timedelta(days=day)
        for k in range(48):
            if day == 1 and k == 10:
                continue  # one missing interval on the second day
            t = datetime.combine(d, datetime.min.time(), UTC) + timedelta(minutes=30 * k)
            rel = f"raw/gpm/imerg/hh_{t:%Y%m%dT%H%M}.HDF5"
            (env.root / rel).parent.mkdir(parents=True, exist_ok=True)
            write_synthetic_half_hour(env.root / rel, t, 2.0)
            env.db.add(DataAcquisition(collection_id=hcol.id, provider="GPM", granule_id=f"HH-{t:%Y%m%dT%H%M}", product_type="IMERG", status="VALIDATED",
                                       local_file_path=rel, acquisition_start=t))
    env.db.commit()


def test_new_stages_register_aligned_rasters_and_labelled_features(env):
    a = make_area(env, SERIES_AREA, name="series")
    place_external(env)
    seed_series(env)
    rid = process(env, a, stages=["SMAP", "SOIL", "LAND_COVER", "LITHOLOGY", "NDVI", "DISTANCES", "REFERENCE_GRID", "FEATURES", "MANIFEST", "QUALITY"])
    run, st = stages(env, rid)
    assert st["LITHOLOGY"] == "DONE" and st["NDVI"] == "DONE" and st["SOIL"] == "DONE" and st["LAND_COVER"] == "DONE"
    assert st["DISTANCES"] == "PARTIAL" and st["SMAP"] in ("DONE", "PARTIAL") and st["REFERENCE_GRID"] == "DONE" and st["MANIFEST"] == "DONE"
    m = manifest(env, a)
    e = {x["layer_type"]: x for x in m["entries"]}
    for k in ("LITHOLOGY", "NDVI", "DISTANCE_RIVER", "DISTANCE_FAULT", "SOIL", "LAND_COVER"):
        assert e[k]["status"] == "PROCESSED" and e[k]["on_reference_grid"] and e[k]["synthetic"] is True, k
    assert e["DISTANCE_ROAD"]["status"] == "NOT_AVAILABLE" and "no road" in e["DISTANCE_ROAD"]["reason"]  # missing vectors: reported, not zero
    assert e["DISTANCE_RIVER"]["units"] == "metre" and e["NDVI"]["temporal_kind"] == "dynamic" and e["LITHOLOGY"]["temporal_kind"] == "static"
    assert e["SMAP_SOIL_MOISTURE"]["kind"] == "series" and e["SMAP_SOIL_MOISTURE"]["temporal_kind"] == "dynamic" and not e["SMAP_SOIL_MOISTURE"]["on_reference_grid"]

    layers = env.client.get(f"{BASE}/areas/{a.id}/layers").json()["items"]
    by = {}
    for l in layers:
        by.setdefault(l["layer_type"], []).append(l)
    lith = by["LITHOLOGY"][0]
    assert lith["has_raster"] and lith["aligned"]
    lg = env.client.get(f"{BASE}/layers/{lith['id']}/legend").json()
    assert lg["kind"] == "categorical" and {c["id"] for c in lg["classes"]} == {10, 20, 30}
    assert {c["name"] for c in lg["classes"]} == {"synthetic unit A", "synthetic unit B", "synthetic unit C"}  # names come only from the user legend
    for key in ("LITHOLOGY", "NDVI", "DISTANCE_RIVER", "SOIL", "LAND_COVER"):
        l = by[key][0]
        assert l["has_raster"], key
        png = env.client.get(f"{BASE}/layers/{l['id']}/preview")
        assert png.status_code == 200 and png.content[:4] == b"\x89PNG" and png.headers["x-data-origin"] == "SYNTHETIC_FIXTURE", key

    # clipped class raster: class ids are exactly the source ids, on the grid and in the native clip
    lc = env.db.scalars(select(EnvironmentalLayer).where(EnvironmentalLayer.layer_type == "LAND_COVER", EnvironmentalLayer.status == "PROCESSED")).first()
    for rel in (lc.file_path, lc.aligned_file_path):
        with rasterio.open(storage.resolve_output(env.root, rel)) as s:
            ids = set(np.unique(s.read(1)).tolist()) - {int(s.nodata)} if s.nodata is not None else set(np.unique(s.read(1)).tolist())
        assert ids <= {10, 40}, rel
    feats = {g["group"]: g for g in env.client.get(f"{BASE}/areas/{a.id}/features").json()["groups"]}
    for g in ("smap", "lithology", "vegetation", "distances", "soil", "land_cover"):
        assert feats[g]["status"] in ("PROCESSED", "PARTIALLY_PROCESSED") and feats[g]["data_origin"] == "SYNTHETIC_FIXTURE", g
    assert not any(b in n for n in names(feats) for b in ("risk", "probability", "susceptibility", "prediction", "score"))
    d = feats["distances"]["values"]
    assert d, "distance statistics present"
    # series: SMAP missing day stays missing
    sm = next(l for l in layers if l["layer_type"] == "SMAP_SOIL_MOISTURE")
    daily = sm["statistics"]["daily"]
    gap = next(x for x in daily if x["date"] == "2024-02-03")
    assert gap["observed"] is False and gap["soil_moisture"] is None


def test_second_run_reuses_new_stage_outputs(env):
    a = make_area(env, SERIES_AREA, name="series2")
    place_external(env)
    seed_series(env)
    chosen = ["SMAP", "LITHOLOGY", "NDVI", "DISTANCES", "REFERENCE_GRID", "FEATURES", "MANIFEST"]
    process(env, a, stages=chosen)
    _, st = stages(env, process(env, a, stages=chosen))
    assert st["LITHOLOGY"] == st["NDVI"] == st["DISTANCES"] == st["SMAP"] == "SKIPPED"
    run2 = env.client.get(f"{BASE}/processing-runs/{[x for x in env.client.get(f'{BASE}/processing-runs').json()['items']][0]['id']}").json()
    assert next(s for s in run2["stages"] if s["name"] == "REFERENCE_GRID")["message"].endswith("(0 newly aligned)")
    _, st3 = stages(env, process(env, a, stages=chosen, force=True))
    assert st3["LITHOLOGY"] == "DONE"


def test_half_hourly_option_keeps_missing_intervals_missing(env):
    a = make_area(env, SERIES_AREA, name="hh")
    seed_series(env)
    _, st_daily = stages(env, process(env, a, stages=["RAINFALL"]))
    assert st_daily["RAINFALL"] == "NOT_AVAILABLE"  # daily is the default and no daily product is present
    rid = process(env, a, stages=["RAINFALL"], rainfall_resolution="half_hourly", start_date="2024-03-01", end_date="2024-03-02")
    run, st = stages(env, rid)
    assert st["RAINFALL"] == "PARTIAL"
    r = env.client.get(f"{BASE}/areas/{a.id}/rainfall").json()
    d1 = next(p for p in r["daily"] if p["date"] == "2024-03-01")
    d2 = next(p for p in r["daily"] if p["date"] == "2024-03-02")
    assert d1["observed"] and d1["precipitation_mm"] == pytest.approx(48.0)  # 48 intervals x 2 mm/hr x 0.5 h
    assert d2["observed"] is False and d2["precipitation_mm"] is None  # one missing interval: the day is missing, never scaled or zero


def test_all_nodata_ndvi_is_not_available_with_a_reason(env):
    a = make_area(env, SERIES_AREA, name="nodata")
    nd = storage.external_dir(env.root, "ndvi")
    p = xs.make_ndvi_raster(nd, (116.5, 5.0, 116.6, 5.1), "EPSG:4326", shape=(10, 10))
    with rasterio.open(p, "r+") as s:
        s.write(np.full((1, 10, 10), np.nan, dtype="float32"))
    run, st = stages(env, process(env, a, stages=["NDVI", "FEATURES", "MANIFEST"]))
    assert st["NDVI"] == "NOT_AVAILABLE"
    e = {x["layer_type"]: x for x in manifest(env, a)["entries"]}
    assert e["NDVI"]["status"] == "NOT_AVAILABLE" and e["NDVI"]["reason"] and e["NDVI"]["file"] is None


def test_stage_selection_validates_new_names(env):
    a = make_area(env)
    assert env.client.post(f"{BASE}/areas/{a.id}/process", json={"stages": ["SMAP", "MANIFEST"]}).status_code == 202
    assert env.client.post(f"{BASE}/areas/{uuid.uuid4()}/process", json={"stages": ["SMAP"]}).status_code == 404
