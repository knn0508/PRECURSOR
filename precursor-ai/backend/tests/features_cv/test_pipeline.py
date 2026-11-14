"""Feature extraction pipeline on SYNTHETIC Phase-4-style stacks. Not real-data validation."""
import json
import uuid

import numpy as np
import pytest
import rasterio

from app.services.features_cv.pipeline import read_features_manifest, run_extraction
from app.services.features_cv.registry import DEFAULT_PARAMS
from app.services.features_cv.types import FEATURE_SCHEMA_VERSION, FeatureError, NotAvailable
from tests.features_cv.synth import ZONE39, ZONE50, write_stack

REF_FEATURES = {"local_relief_w5", "terrain_ruggedness_index", "curvature_laplacian_s1", "slope_break", "lineament_density_w15"}


def by_name(m):
    return {f["name"]: f for f in m["features"]}


def test_manifest_contents_and_reference_grid_files(tmp_path):
    area, g, _ = write_stack(tmp_path)
    m = run_extraction(tmp_path, area)
    f = by_name(m)
    assert REF_FEATURES <= {n for n, x in f.items() if x["status"] == "DONE"}
    assert m["feature_schema_version"] == FEATURE_SCHEMA_VERSION and m["code_version"].startswith("features_cv/")
    assert m["source"]["phase4_manifest_sha256"] and m["seed"] is None and m["randomness"].startswith("none")
    assert m["contains_synthetic_data"] is True and m["real_data_validation"] == "NOT_PERFORMED" and m["validation_status"] == "NOT_VALIDATED"
    assert m["grid"]["crs"] == "EPSG:32650" and m["parameters"]["relief_window_px"] == DEFAULT_PARAMS["relief_window_px"]
    for n in REF_FEATURES:
        p = tmp_path / "processed" / "features" / str(area) / "rasters" / f"{n}.tif"
        with rasterio.open(p) as ds:  # CRS and transform preserved exactly
            assert ds.crs.to_string() == g["crs"] and tuple(ds.transform)[:6] == tuple(g["transform"]) and (ds.width, ds.height) == (96, 96)
            assert ds.tags()["feature"] == n and ds.tags()["synthetic_inputs"] == "1" and ds.tags()["container"] in ("COG", "GTiff-tiled")
        assert f[n]["grid"] == "reference" and f[n]["source_synthetic"] is True and f[n]["array_sha256"]
    assert read_features_manifest(tmp_path, area)["area_id"] == str(area)


def test_texture_features_live_on_a_declared_block_grid(tmp_path):
    area, g, _ = write_stack(tmp_path)
    f = by_name(run_extraction(tmp_path, area))
    t = f["glcm_slope_contrast_w16"]
    assert t["status"] == "DONE" and t["grid"] == "block" and t["shape"] == [6, 6] and t["resolution_m"] == 16 * 30.0
    assert t["details"]["quantisation"]["fixed_bounds"] is True and (t["details"]["quantisation"]["vmin"], t["details"]["quantisation"]["vmax"]) == (0.0, 90.0)
    with rasterio.open(tmp_path / "processed" / "features" / str(area) / "rasters" / "glcm_slope_contrast_w16.tif") as ds:
        assert ds.transform.a == 16 * 30.0 and ds.transform.c == g["transform"][2] and ds.crs.to_string() == g["crs"]


def test_deterministic_rerun_gives_identical_arrays(tmp_path):
    area, _, _ = write_stack(tmp_path)
    a = run_extraction(tmp_path, area)
    b = run_extraction(tmp_path, area)
    assert {n: x.get("array_sha256") for n, x in by_name(a).items()} == {n: x.get("array_sha256") for n, x in by_name(b).items()}


def test_change_features_are_not_available_and_insar_is_never_used_as_input(tmp_path):
    area, _, _ = write_stack(tmp_path)
    f = by_name(run_extraction(tmp_path, area))
    for n in ("ndvi_difference", "coherence_change", "insar_velocity_gradient"):
        assert f[n]["status"] == "NOT_AVAILABLE" and f[n]["reason"]


def test_missing_slope_layer_is_rederived_and_stated(tmp_path):
    area, _, _ = write_stack(tmp_path, slope_layer=False)
    f = by_name(run_extraction(tmp_path, area))
    assert f["slope_break"]["status"] == "DONE" and any("re-derived" in n for n in f["slope_break"]["notes"])
    assert f["glcm_slope_contrast_w16"]["status"] == "NOT_AVAILABLE"  # texture needs the SLOPE layer itself


def test_nodata_hole_propagates_as_nan_never_zero(tmp_path):
    area, _, _ = write_stack(tmp_path, nan_hole=(slice(40, 52), slice(40, 52)))
    run_extraction(tmp_path, area)
    for n in ("local_relief_w5", "terrain_ruggedness_index", "curvature_laplacian_s1", "slope_break", "lineament_density_w15"):
        with rasterio.open(tmp_path / "processed" / "features" / str(area) / "rasters" / f"{n}.tif") as ds:
            a = ds.read(1)
        assert np.isnan(a[45, 45]), n
        assert np.isfinite(a[20, 20]), n


def test_two_aois_in_different_utm_zones(tmp_path):
    a50, g50, _ = write_stack(tmp_path, **ZONE50)
    a39, g39, _ = write_stack(tmp_path, **ZONE39)
    m50, m39 = run_extraction(tmp_path, a50), run_extraction(tmp_path, a39)
    assert m50["grid"]["crs"] == "EPSG:32650" and m39["grid"]["crs"] == "EPSG:32639"
    assert REF_FEATURES <= {n for n, x in by_name(m50).items() if x["status"] == "DONE"} and REF_FEATURES <= {n for n, x in by_name(m39).items() if x["status"] == "DONE"}
    # identical terrain on identical grids gives identical feature values regardless of the CRS: metre-based, not CRS-specific
    assert by_name(m50)["local_relief_w5"]["array_sha256"] == by_name(m39)["local_relief_w5"]["array_sha256"]
    with rasterio.open(tmp_path / "processed" / "features" / str(a39) / "rasters" / "slope_break.tif") as ds:
        assert ds.crs.to_epsg() == 32639


def test_aoi_smaller_than_one_cell_does_not_crash(tmp_path):
    area, _, _ = write_stack(tmp_path, n=1)  # a 1 x 1 reference grid (Phase 4 warns but still builds it)
    m = run_extraction(tmp_path, area)
    f = by_name(m)
    assert f["local_relief_w5"]["status"] == "DONE" and f["local_relief_w5"]["valid_percent"] == 0.0 and f["local_relief_w5"]["min"] is None
    assert f["terrain_ruggedness_index"]["valid_percent"] == 0.0
    assert f["glcm_slope_contrast_w16"]["status"] == "NOT_AVAILABLE"  # 1x1 raster cannot hold a texture block


def test_small_raster_features_are_nan_not_zero(tmp_path):
    area, _, _ = write_stack(tmp_path, n=4)
    f = by_name(run_extraction(tmp_path, area))
    assert f["terrain_ruggedness_index"]["valid_percent"] == pytest.approx(100 * 4 / 16)  # only the 2x2 interior is defined


def test_normalisation_parameters_are_recorded_not_applied_to_the_files(tmp_path):
    area, _, _ = write_stack(tmp_path)
    m = run_extraction(tmp_path, area, normalise="zscore")
    f = by_name(m)["local_relief_w5"]
    assert f["normalisation"]["method"] == "zscore" and f["normalisation"]["n_valid"] > 0
    with rasterio.open(tmp_path / "processed" / "features" / str(area) / "rasters" / "local_relief_w5.tif") as ds:
        assert np.nanmin(ds.read(1)) >= 0  # relief is still raw metres
    with pytest.raises(FeatureError):
        run_extraction(tmp_path, area, normalise="robust")  # bad method -> clear error


def test_bad_parameters_and_missing_stack(tmp_path):
    area, _, _ = write_stack(tmp_path)
    with pytest.raises(FeatureError, match="unknown extraction parameter"):
        run_extraction(tmp_path, area, {"nope": 1})
    with pytest.raises(FeatureError, match="odd integer"):
        run_extraction(tmp_path, area, {"relief_window_px": 4})
    ghost = uuid.uuid4()
    with pytest.raises(NotAvailable):
        run_extraction(tmp_path, ghost)
    with pytest.raises(NotAvailable):
        read_features_manifest(tmp_path, ghost)
    assert not (tmp_path / "processed" / "features" / str(ghost)).exists()  # failed/read paths create nothing


def test_stack_without_reference_grid_or_rasters_is_not_available(tmp_path):
    area, _, _ = write_stack(tmp_path)
    mp = tmp_path / "processed" / "environmental" / str(area) / "features" / "manifest.json"
    m = json.loads(mp.read_text())
    mp.write_text(json.dumps({**m, "reference_grid": None}))
    with pytest.raises(NotAvailable, match="reference grid"):
        run_extraction(tmp_path, area)
    mp.write_text(json.dumps({**m, "entries": [{**e, "on_reference_grid": False} for e in m["entries"]]}))
    with pytest.raises(NotAvailable, match="no raster layer"):
        run_extraction(tmp_path, area)


def test_grid_mismatch_between_manifest_and_raster_is_refused(tmp_path):
    area, _, _ = write_stack(tmp_path)
    mp = tmp_path / "processed" / "environmental" / str(area) / "features" / "manifest.json"
    m = json.loads(mp.read_text())
    m["reference_grid"]["width"] = 95
    mp.write_text(json.dumps(m))
    with pytest.raises(FeatureError, match="grid mismatch"):
        run_extraction(tmp_path, area)


def test_unsafe_file_name_in_manifest_is_skipped_not_followed(tmp_path):
    area, _, _ = write_stack(tmp_path)
    mp = tmp_path / "processed" / "environmental" / str(area) / "features" / "manifest.json"
    m = json.loads(mp.read_text())
    for e in m["entries"]:
        if e["layer_type"] == "NDVI":
            e["file"] = "../../../../etc/passwd"
    mp.write_text(json.dumps(m))
    out = run_extraction(tmp_path, area)
    assert any(s["layer"] == "NDVI" and "unsafe" in s["reason"] for s in out["skipped_layers"])
