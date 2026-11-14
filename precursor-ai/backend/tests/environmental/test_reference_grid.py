"""Reference grid + alignment tests on SYNTHETIC rasters (not real data)."""
import json

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from shapely.geometry import Polygon, box

from app.services.environmental.providers.synthetic import write_synthetic_raster
from app.services.environmental.raster.reference_grid import (
    align_layer_to_reference, build_reference_grid, choose_projected_crs)
from app.services.environmental.types import EnvError, LayerKind, NotAvailable

AOI = (116.10, 5.60, 116.20, 5.70)  # zone 50N


def test_utm_zone_rule_and_hemisphere():
    assert choose_projected_crs(AOI).epsg == 32650
    assert choose_projected_crs((49.8, 40.3, 49.9, 40.4)).epsg == 32639
    assert choose_projected_crs((-70.1, -33.5, -70.0, -33.4)).epsg == 32719  # south
    assert choose_projected_crs(box(*AOI)).zone == 50


def test_norway_and_svalbard_exceptions():
    assert choose_projected_crs((5.0, 60.0, 5.2, 60.1)).zone == 32
    assert choose_projected_crs((15.0, 78.0, 15.2, 78.1)).zone == 33
    assert choose_projected_crs((5.0, 50.0, 5.2, 50.1)).zone == 31  # no exception outside the box


def test_different_zones_give_different_crs_and_metre_extent():
    a = build_reference_grid((116.10, 5.60, 116.20, 5.70))
    b = build_reference_grid((49.80, 40.30, 49.90, 40.40))
    assert a.epsg != b.epsg
    # 0.1 deg lat ~ 11.06 km at the equator; ~11.1 km at 40N, so extents are metric not degree-sized
    for g, lat in ((a, 5.65), (b, 40.35)):
        h_m = g.bounds[3] - g.bounds[1]
        assert 10_900 < h_m < 11_500
        assert g.grid.height * g.resolution_m == pytest.approx(h_m)
        assert g.grid.resolution()["x"] == 30.0


def test_straddling_zone_boundary_warns_and_keeps_centroid_zone():
    ch = choose_projected_crs((113.9, 5.0, 114.5, 5.2))  # boundary at 114 E (zones 49/50)
    assert ch.zone == 50 and any("49" in w and "50" in w and "distortion" in w for w in ch.warnings)


def test_polar_and_antimeridian_and_invalid():
    n = choose_projected_crs((10, 85, 11, 86))
    assert n.kind == "polar" and n.epsg == 3413 and n.warnings
    assert choose_projected_crs((10, -86, 11, -85)).epsg == 3031
    with pytest.raises(EnvError, match="antimeridian"):
        choose_projected_crs((179.0, 10, -179.0, 11))
    with pytest.raises(EnvError):
        choose_projected_crs((1, 2, float("nan"), 3))
    with pytest.raises(EnvError):
        choose_projected_crs(Polygon())


def test_user_crs_validation():
    assert build_reference_grid(AOI, crs="EPSG:32650").chosen_by == "user"
    with pytest.raises(EnvError, match="projected"):
        build_reference_grid(AOI, crs="EPSG:4326")
    with pytest.raises(EnvError):
        build_reference_grid(AOI, crs="EPSG:99999999")
    with pytest.raises(EnvError, match="metre"):
        build_reference_grid(AOI, crs="EPSG:2272")  # NAD83 / Pennsylvania South, US survey feet
    with pytest.raises(EnvError):
        build_reference_grid(AOI, resolution_m=0)


def test_deterministic_and_json_serialisable():
    a, b = build_reference_grid(AOI).to_dict(), build_reference_grid(AOI).to_dict()
    assert a == b and json.dumps(a)
    assert a["resolution"]["unit"] == "metre" and len(a["transform"]) == 6
    assert a["bounds"][0] % 30 == 0 and a["bounds"][1] % 30 == 0


def test_tiny_aoi_gives_one_cell_with_warning():
    g = build_reference_grid((116.10, 5.60, 116.10001, 5.60001))
    assert (g.grid.width, g.grid.height) in ((1, 1), (2, 1), (1, 2), (2, 2))
    assert any("smaller than one" in w for w in g.warnings)


def test_max_pixels_coarsens_with_warning():
    g = build_reference_grid(AOI, max_pixels=10_000)
    assert g.grid.width * g.grid.height <= 10_000 and g.resolution_m > 30
    assert any("coarsened" in w for w in g.warnings)


# ---------- alignment ----------
def _utm_grid_src(tmp_path, data, name="u.tif", pixel=30.0, **kw):
    tr = Transformer.from_crs(4326, 32650, always_xy=True)
    x, y = tr.transform(116.08, 5.72)
    return write_synthetic_raster(tmp_path / name, data, crs="EPSG:32650", west=x, north=y, pixel=pixel, **kw)


def test_mixed_crs_inputs_align_to_same_grid(tmp_path):
    ref = build_reference_grid(AOI)
    dem = write_synthetic_raster(tmp_path / "dem.tif", np.full((400, 400), 100.0, "float32"), west=116.05, north=5.75, pixel=0.00045)
    utm = _utm_grid_src(tmp_path, np.full((600, 600), 50.0, "float32"))
    for p, v in ((dem, 100.0), (utm, 50.0)):
        r = align_layer_to_reference(p, ref, LayerKind.ELEVATION, tmp_path / f"o_{p.name}")
        with rasterio.open(r.path) as s:
            assert (s.width, s.height) == (ref.grid.width, ref.grid.height) and s.crs.to_epsg() == 32650
            assert np.nanmedian(s.read(1)) == pytest.approx(v, abs=1e-3)
        assert r.quality.valid_percent > 95 and r.resampling == "bilinear"
        assert any("does not add information" in w for w in r.quality.warnings)


def test_categorical_ids_unchanged_integer_dtype(tmp_path):
    ref = build_reference_grid(AOI)
    ids = (np.arange(600)[None, :] // 100 * 10 + 10).astype("uint8") * np.ones((600, 1), "uint8")
    src = _utm_grid_src(tmp_path, ids, nodata=0)
    r = align_layer_to_reference(src, ref, LayerKind.LAND_COVER, tmp_path / "lc.tif", aoi_wgs84=box(*AOI))
    with rasterio.open(r.path) as s:
        out = s.read(1)
        assert s.dtypes[0] == "uint8" and s.nodata == 0
    assert set(np.unique(out[out != 0])) <= set(np.unique(ids)) and r.resampling == "nearest"


def test_aspect_359_and_1_not_averaged(tmp_path):
    ref = build_reference_grid(AOI, resolution_m=60.0)  # coarser than source: neighbours are blended
    a = np.where(np.arange(600)[None, :] % 2 == 0, 359.0, 1.0).astype("float32") * np.ones((600, 1), "float32")
    r = align_layer_to_reference(_utm_grid_src(tmp_path, a), ref, LayerKind.ASPECT, tmp_path / "a.tif")
    with rasterio.open(r.path) as s:
        v = s.read(1)
    v = v[np.isfinite(v)]
    assert v.size and np.all((v < 20) | (v > 340))


def test_all_nodata_source_reported_not_zero(tmp_path):
    ref = build_reference_grid(AOI)
    src = _utm_grid_src(tmp_path, np.full((600, 600), -9999.0, "float32"), nodata=-9999.0)
    r = align_layer_to_reference(src, ref, LayerKind.ELEVATION, tmp_path / "n.tif")
    assert r.quality.valid_percent == 0 and any("no valid pixel" in w for w in r.quality.warnings)
    with rasterio.open(r.path) as s:
        assert np.isnan(s.read(1)).all()


def test_no_overlap_not_available(tmp_path):
    ref = build_reference_grid(AOI)
    far = write_synthetic_raster(tmp_path / "far.tif", np.ones((10, 10), "float32"), west=10.0, north=10.0, pixel=0.01)
    with pytest.raises(NotAvailable, match="overlap"):
        align_layer_to_reference(far, ref, LayerKind.ELEVATION, tmp_path / "x.tif")


def test_oversampling_warning(tmp_path):
    ref = build_reference_grid(AOI, resolution_m=10.0)
    src = _utm_grid_src(tmp_path, np.full((600, 600), 5.0, "float32"), pixel=30.0)
    r = align_layer_to_reference(src, ref, LayerKind.ELEVATION, tmp_path / "o.tif")
    assert any("OVERSAMPLING" in w for w in r.quality.warnings)
    r2 = align_layer_to_reference(src, build_reference_grid(AOI), LayerKind.ELEVATION, tmp_path / "o2.tif")
    assert not any("OVERSAMPLING" in w for w in r2.quality.warnings)


def test_aoi_polygon_mask_applied(tmp_path):
    tri = Polygon([(116.10, 5.60), (116.20, 5.60), (116.10, 5.70)])
    ref = build_reference_grid(tri)
    src = _utm_grid_src(tmp_path, np.full((600, 600), 5.0, "float32"))
    r = align_layer_to_reference(src, ref, LayerKind.ELEVATION, tmp_path / "t.tif", aoi_wgs84=tri)
    assert 30 < r.quality.valid_percent < 70
