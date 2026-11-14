"""Tiling, normalisation, GLCM texture, change-detection guard, registry and ModelInputSpec. SYNTHETIC arrays only."""
from datetime import UTC, datetime

import numpy as np
import pytest
import rasterio
from rasterio.windows import Window

from app.services.features_cv import change, texture
from app.services.features_cv.registry import REGISTRY, ChangeExtractor, ExtractionContext, FeatureRegistry, TerrainExtractor
from app.services.features_cv.schema import ModelInputSpec
from app.services.features_cv.tiling import assert_same_grid, fit_normalisation, iter_tiles, read_window, tiled_apply
from app.services.features_cv.types import (
    FEATURE_SCHEMA_VERSION, ChangeDetectionRefused, FeatureError, FeatureSpec, forbidden_names)
from tests.features_cv.synth import grid_dict, write_stack


# ---------------- tiling ----------------
def test_tiles_cover_the_raster_exactly_once():
    cover = np.zeros((23, 37), int)
    for t in iter_tiles(23, 37, 10, 3):
        r0, r1, c0, c1 = t.core
        cover[r0:r1, c0:c1] += 1
        R0, R1, C0, C1 = t.read
        assert R0 <= r0 and R1 >= r1 and C0 <= c0 and C1 >= c1 and R0 >= 0 and C1 <= 37
    assert (cover == 1).all()


def test_tiling_rejects_bad_arguments():
    with pytest.raises(FeatureError):
        list(iter_tiles(0, 5, 2, 0))
    with pytest.raises(FeatureError):
        list(iter_tiles(5, 5, 0, 0))
    with pytest.raises(FeatureError):
        tiled_apply(np.zeros(4), lambda b, r: b)
    with pytest.raises(FeatureError):
        tiled_apply(np.zeros((4, 4)), lambda b, r: b[:1], tile=2)


def test_tiled_apply_leaves_unwritten_pixels_missing_not_zero():
    out = tiled_apply(np.ones((6, 6), np.float32), lambda b, r: np.full(b.shape, np.nan, np.float32), tile=3)
    assert np.isnan(out).all()


def test_read_window_preserves_crs_and_transform(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=32)
    p = tmp_path / "processed" / "environmental" / str(area) / "aligned" / "elevation.tif"
    arr, tf = read_window(p, Window(4, 6, 8, 5))
    assert arr.shape == (5, 8) and np.allclose(arr, arrays["ELEVATION"][6:11, 4:12])
    assert tf.c == pytest.approx(g["transform"][2] + 4 * 30.0) and tf.f == pytest.approx(g["transform"][5] - 6 * 30.0)
    with rasterio.open(p) as ds:
        assert ds.crs.to_string() == g["crs"]


def test_assert_same_grid_refuses_mismatch_and_accepts_equal():
    a = grid_dict(32650, 600000.0, 630000.0, 10, 30.0)
    assert_same_grid(a, dict(a))
    for key, val in (("crs", "EPSG:32651"), ("width", 11), ("height", 9)):
        with pytest.raises(FeatureError, match="grid mismatch"):
            assert_same_grid(a, {**a, key: val})
    with pytest.raises(FeatureError, match="transform"):
        assert_same_grid(a, {**a, "transform": [30.0, 0, 600030.0, 0, -30.0, 630000.0]})


def test_normalisation_records_parameters_ignores_nan_and_inverts():
    rng = np.random.default_rng(0)
    a = rng.normal(50, 5, (30, 30)).astype(np.float32)
    a[3, 3] = np.nan
    n = fit_normalisation(a, "zscore")
    assert n.n_valid == 899 and n.params["mean"] == pytest.approx(float(np.nanmean(a)), rel=1e-5)
    out = n.apply(a)
    assert np.isnan(out[3, 3]) and np.nanmean(out) == pytest.approx(0, abs=1e-4) and np.nanstd(out) == pytest.approx(1, rel=1e-4)
    assert np.allclose(n.invert(out), a, equal_nan=True, atol=1e-3)
    mm = fit_normalisation(a, "minmax")
    o = mm.apply(a)
    assert np.nanmin(o) == pytest.approx(0, abs=1e-6) and np.nanmax(o) == pytest.approx(1, abs=1e-6)
    assert set(n.to_dict()) == {"method", "params", "n_valid"}


@pytest.mark.parametrize("arr,method", [(np.full((4, 4), 2.0), "zscore"), (np.full((4, 4), 2.0), "minmax"), (np.full((4, 4), np.nan), "zscore"), (np.ones((2, 2)), "robust")])
def test_normalisation_refuses_constant_empty_or_unknown(arr, method):
    with pytest.raises(FeatureError):
        fit_normalisation(arr, method)


# ---------------- texture ----------------
def test_glcm_constant_window_oracle():
    res = texture.glcm_blocks(_two_level(8, constant=True), 8, levels=4, vmin=0, vmax=10)
    assert res.layers["contrast"][0, 0] == 0.0 and res.layers["homogeneity"][0, 0] == pytest.approx(1.0) and res.layers["energy"][0, 0] == pytest.approx(1.0)
    assert np.isnan(res.layers["correlation"][0, 0])  # convention value 1.0 is NOT reported for a constant window


def _two_level(n, constant=False):
    a = np.zeros((n, n))
    if constant:
        return a + 5.0
    a[(np.indices((n, n)).sum(axis=0)) % 2 == 1] = 10.0
    return a


def test_glcm_checkerboard_contrast_is_half_of_max_squared():
    lv = 8
    res = texture.glcm_blocks(_two_level(8), 8, levels=lv, vmin=0, vmax=10)
    # pairs at 0 and 90 degrees always differ by (levels-1); at 45/135 degrees they are equal -> mean = (L-1)^2 / 2
    assert res.layers["contrast"][0, 0] == pytest.approx((lv - 1) ** 2 / 2, rel=1e-6)
    assert res.layers["dissimilarity"][0, 0] == pytest.approx((lv - 1) / 2, rel=1e-6)


def test_glcm_block_grid_shape_nan_blocks_and_clipping_count():
    a = np.random.default_rng(0).uniform(0, 1, (20, 35))
    a[2, 2] = np.nan  # poisons block (0,0) only
    a[18, 30] = 5.0  # outside the stated bounds -> clipped, counted
    r = texture.glcm_blocks(a, 8, levels=8, vmin=0, vmax=1)
    assert r.layers["contrast"].shape == (2, 4)  # partial edge blocks dropped, not padded
    assert np.isnan(r.layers["contrast"][0, 0]) and not np.isnan(r.layers["contrast"][1, 2])
    assert r.n_blocks == 8 and r.n_blocks_valid == 7 and r.n_clipped == 1 and (r.vmin, r.vmax, r.levels, r.stride) == (0, 1, 8, 8)


def test_glcm_is_deterministic_and_validates():
    a = np.random.default_rng(1).uniform(0, 1, (16, 16))
    x, y = texture.glcm_blocks(a, 8, levels=8, vmin=0, vmax=1), texture.glcm_blocks(a, 8, levels=8, vmin=0, vmax=1)
    for p in texture.PROPS:
        assert np.array_equal(x.layers[p], y.layers[p], equal_nan=True)
    for kw in ({"levels": 1}, {"levels": 300}, {"distance": 0}, {"distance": 8}):
        with pytest.raises(FeatureError):
            texture.glcm_blocks(a, 8, **{"vmin": 0, "vmax": 1, **kw})
    with pytest.raises(FeatureError):
        texture.glcm_blocks(a, 2, vmin=0, vmax=1)
    with pytest.raises(FeatureError, match="constant"):
        texture.glcm_blocks(np.ones((16, 16)), 8)
    with pytest.raises(FeatureError, match="no valid"):
        texture.glcm_blocks(np.full((16, 16), np.nan), 8)
    with pytest.raises(FeatureError):
        texture.quantise(a, 1.0, 1.0, 8)


# ---------------- change detection guard ----------------
G = grid_dict(32650, 600000.0, 630000.0, 8, 30.0)
D1, D2 = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 3, 1, tzinfo=UTC)


def di(date=D1, origin="REAL_SATELLITE", units="NDVI", layer="NDVI", grid=G, synthetic=False, val=0.4):
    return change.DatedInput(layer, np.full((8, 8), val, np.float32), date, origin, units, grid, synthetic)


def test_change_features_computed_only_from_two_dated_real_inputs():
    arr, info = change.ndvi_difference(di(D1, val=0.4), di(D2, val=0.55))  # arguments out of order is fine: sorted by date
    assert np.allclose(arr, 0.15, atol=1e-6) and info["earlier"].startswith("2024-01-01") and info["later"].startswith("2024-03-01")
    arr2, _ = change.ndvi_difference(di(D2, val=0.55), di(D1, val=0.4))
    assert np.allclose(arr2, 0.15, atol=1e-6)
    cc, _ = change.coherence_change(di(D1, units="", layer="INSAR_COHERENCE", val=0.8), di(D2, units="", layer="INSAR_COHERENCE", val=0.5))
    assert np.allclose(cc, -0.3, atol=1e-6)


@pytest.mark.parametrize("a,b,fragment", [
    (di(origin="SYNTHETIC_FIXTURE", synthetic=True), di(D2), "synthetic"),
    (di(D1), di(D2, origin="LOCAL_UNVERIFIED"), "LOCAL_UNVERIFIED"),
    (di(date=None), di(D2), "no acquisition date"),
    (di(D1), di(D1), "same date"),
    (di(D1, layer="NDVI"), di(D2, layer="INSAR_COHERENCE"), "layer types differ"),
    (di(D1, units="NDVI"), di(D2, units="x"), "units differ"),
    (di(D1), di(D2, grid={**G, "width": 9}), "grid mismatch"),
])
def test_change_guard_refuses_and_names_the_reason(a, b, fragment):
    with pytest.raises(ChangeDetectionRefused, match=fragment):
        change.ndvi_difference(a, b)


def test_change_guard_lists_every_reason_at_once():
    with pytest.raises(ChangeDetectionRefused) as e:
        change.ndvi_difference(di(date=None, origin="SYNTHETIC_FIXTURE", synthetic=True), di(D1, units="x"))
    msg = str(e.value)
    assert "no acquisition date" in msg and "synthetic" in msg and "units differ" in msg


def test_velocity_gradient_needs_one_real_dated_input():
    dx = dy = np.full(8, 30.0)
    v = di(units="mm/yr", layer="INSAR_VELOCITY")
    v.array = (np.arange(8)[None, :] * 3.0 * np.ones((8, 1))).astype(np.float32)  # 3 mm/yr per pixel -> 0.1 per metre
    out, info = change.velocity_gradient(v, dx, dy)
    assert out[4, 4] == pytest.approx(0.1, rel=1e-5) and info["units"] == "mm/yr per metre"
    with pytest.raises(ChangeDetectionRefused):
        change.velocity_gradient(di(origin="SYNTHETIC_FIXTURE", synthetic=True), dx, dy)


def test_change_extractor_reports_not_available_when_the_stack_holds_one_input_per_layer():
    ctx = ExtractionContext({}, {}, G)
    res, skipped = ChangeExtractor().extract(ctx)
    assert res == [] and {s["feature"] for s in skipped} == {"ndvi_difference", "coherence_change", "insar_velocity_gradient"}
    assert all(s["status"] == "NOT_AVAILABLE" and s["reason"] for s in skipped)


def test_change_extractor_turns_a_refusal_into_not_available_and_computes_real_inputs():
    syn = ExtractionContext({}, {}, G, change_inputs={"NDVI": [di(D1, origin="SYNTHETIC_FIXTURE", synthetic=True), di(D2, origin="SYNTHETIC_FIXTURE", synthetic=True)]})
    res, skipped = ChangeExtractor().extract(syn)
    assert res == [] and any("refused" in s["reason"] and s["feature"] == "ndvi_difference" for s in skipped)
    # TEST_DOUBLE: inputs labelled REAL_SATELLITE inside a unit test purely to exercise the compute path (no real data exists)
    ok = ExtractionContext({}, {}, G, change_inputs={"NDVI": [di(D1, val=0.2), di(D2, val=0.5)]})
    res, skipped = ChangeExtractor().extract(ok)
    assert [r.spec.name for r in res] == ["ndvi_difference"] and np.allclose(res[0].array, 0.3, atol=1e-6)


# ---------------- registry and ModelInputSpec ----------------
def test_registry_has_builtin_extractors_and_refuses_duplicates_and_bad_names():
    assert REGISTRY.names() == ["change", "terrain", "texture"]
    with pytest.raises(FeatureError, match="already registered"):
        REGISTRY.register(TerrainExtractor())
    with pytest.raises(FeatureError, match="unknown extractor"):
        REGISTRY.get("nope")
    with pytest.raises(FeatureError, match="protocol"):
        FeatureRegistry().register(object())  # type: ignore[arg-type]

    class Bad:
        name = "bad"

        def catalogue(self, params):
            return [FeatureSpec("landslide_risk_index", "terrain", "x", "")]

        def extract(self, ctx):
            return [], []

    with pytest.raises(FeatureError, match="scores"):
        FeatureRegistry().register(Bad())


def test_catalogue_is_parameter_dependent_and_has_no_forbidden_names():
    names = [s.name for s in REGISTRY.catalogue()]
    assert "local_relief_w5" in names and "lineament_density_w15" in names and "glcm_slope_contrast_w16" in names
    assert [s.name for s in REGISTRY.catalogue({"relief_window_px": 7})].count("local_relief_w7") == 1
    assert forbidden_names(names) == []
    assert forbidden_names(["risk_map", "p_probability", "susceptibility_x", "prediction", "danger", "ok_feature"]) == ["danger", "p_probability", "prediction", "risk_map", "susceptibility_x"]


def manifest(names, version=FEATURE_SCHEMA_VERSION, status="DONE", crs="EPSG:32650", res=30.0):
    return {"feature_schema_version": version, "features": [{"name": n, "status": status} for n in names], "grid": {"crs": crs, "resolution_m": res}}


def test_model_input_spec_validates_against_a_manifest():
    spec = ModelInputSpec(["local_relief_w5", "slope_break"], grid_crs="EPSG:32650", grid_resolution_m=30.0)
    spec.validate_against(manifest(["local_relief_w5", "slope_break", "extra"]))
    with pytest.raises(FeatureError, match="missing or not DONE"):
        spec.validate_against(manifest(["local_relief_w5"]))
    with pytest.raises(FeatureError, match="missing or not DONE"):
        spec.validate_against(manifest(["local_relief_w5", "slope_break"], status="NOT_AVAILABLE"))
    with pytest.raises(FeatureError, match="major version"):
        spec.validate_against(manifest(["local_relief_w5", "slope_break"], version="2.0.0"))
    spec.validate_against(manifest(["local_relief_w5", "slope_break"], version="1.7.2"))  # a MINOR change is compatible
    with pytest.raises(FeatureError, match="CRS"):
        spec.validate_against(manifest(["local_relief_w5", "slope_break"], crs="EPSG:32639"))
    with pytest.raises(FeatureError, match="resolution"):
        spec.validate_against(manifest(["local_relief_w5", "slope_break"], res=10.0))


def test_model_input_spec_rejects_bad_names():
    with pytest.raises(FeatureError):
        ModelInputSpec([])
    with pytest.raises(FeatureError):
        ModelInputSpec(["a", "a"])
    with pytest.raises(FeatureError, match="scores"):
        ModelInputSpec(["landslide_probability"])
    assert set(ModelInputSpec(["a"]).to_dict()) >= {"feature_names", "feature_schema_version", "dataset_schema_version", "nodata_policy"}
