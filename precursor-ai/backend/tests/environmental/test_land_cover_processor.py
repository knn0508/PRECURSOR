"""Land-cover processor tests on a SYNTHETIC class-id GeoTIFF (not WorldCover data)."""
import numpy as np
import pytest

from app.services.environmental.features.land_cover_features import land_cover_features
from app.services.environmental.providers.land_cover import WORLDCOVER_LEGEND
from app.services.environmental.providers.synthetic import write_synthetic_land_cover
from app.services.environmental.land_cover.land_cover_processor import process_land_cover
from app.services.environmental.types import DataOrigin, EnvError, NotAvailable

BB = (116.0, 5.0, 116.4, 5.4)


def test_legend_is_official_eleven_classes():
    assert sorted(WORLDCOVER_LEGEND) == [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
    assert WORLDCOVER_LEGEND[95] == ("Mangroves", "#00cf75")


def test_ids_preserved_percentages_sum_and_holes_excluded(tmp_path):
    ids = np.array([[10, 10, 40, 0],  # 0 = declared nodata hole
                    [10, 80, 40, 77],  # 77 = id not in the legend
                    [10, 80, 40, 50],
                    [10, 95, 40, 50]], dtype="uint8")
    p = write_synthetic_land_cover(tmp_path / "lc.tif", ids, west=116.0, north=5.4, pixel=0.1)
    r = process_land_cover([p], BB)
    assert r.valid_pixels == 15 and r.total_pixels == 16
    by = {c["class_id"]: c for c in r.classes}
    assert set(by) == {10, 40, 80, 95, 50} and by[10]["pixels"] == 5 and by[10]["name"] == "Tree cover"
    assert by[10]["percent"] == pytest.approx(100 * 5 / 15)
    assert [u["class_id"] for u in r.unknown_classes] == [77] and any("77" in w for w in r.warnings)
    assert sum(c["percent"] for c in r.classes) + sum(u["percent"] for u in r.unknown_classes) == pytest.approx(100.0)
    assert r.quality.valid_percent == pytest.approx(100 * 15 / 16) and r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE
    assert (r.version, r.year) == ("v200", 2021)
    f = land_cover_features(r)
    assert f["values"]["observation_year"] == 2021 and f["values"]["unknown_class_percent"][77] == pytest.approx(100 / 15)


def test_two_tiles_counts_add(tmp_path):
    a = write_synthetic_land_cover(tmp_path / "a.tif", np.full((2, 4), 10), west=116.0, north=5.4, pixel=0.1)
    b = write_synthetic_land_cover(tmp_path / "b.tif", np.full((2, 4), 30), west=116.0, north=5.2, pixel=0.1)
    r = process_land_cover([a, b], BB)
    assert {c["class_id"]: c["percent"] for c in r.classes} == {10: 50.0, 30: 50.0}
    assert r.quality.aoi_coverage_percent == pytest.approx(100.0)


def test_errors(tmp_path):
    p = write_synthetic_land_cover(tmp_path / "x.tif", np.zeros((4, 4)), west=116.0, north=5.4, pixel=0.1)
    with pytest.raises(EnvError):  # everything nodata is reported, not turned into a distribution
        process_land_cover([p], BB)
    with pytest.raises(NotAvailable):
        process_land_cover([p], (10.0, 10.0, 11.0, 11.0))
    with pytest.raises(ValueError):
        process_land_cover([p], BB, version="v300")


def test_land_cover_map_raster_preserves_ids_and_grid(tmp_path):
    import json
    import rasterio
    from app.services.environmental.providers.synthetic import write_synthetic_land_cover
    ids = np.array([[10, 40, 0], [50, 10, 80]])
    src = write_synthetic_land_cover(tmp_path / "t.tif", ids, west=116.0, north=6.0, pixel=0.1)
    r = process_land_cover([src], (116.0, 5.8, 116.3, 6.0), out_dir=tmp_path / "o")
    (e,) = r.rasters
    json.dumps(e)
    with rasterio.open(e["path"]) as s:
        out = s.read(1)
        assert s.dtypes[0] == "uint8" and s.nodata == 0 and s.bounds.left == pytest.approx(116.0)
        assert "PRECURSOR_SYNTHETIC_FIXTURE" in s.tags() and json.loads(s.tags()["legend"])["10"]["name"]
    assert set(np.unique(out)) == {0, 10, 40, 50, 80}
    assert r.valid_pixels == 5
    assert process_land_cover([src], (116.0, 5.8, 116.3, 6.0)).rasters == []


def test_land_cover_two_aligned_tiles_merge(tmp_path):
    import rasterio
    from app.services.environmental.providers.synthetic import write_synthetic_land_cover
    a = write_synthetic_land_cover(tmp_path / "a.tif", np.full((5, 5), 10), west=116.0, north=6.0, pixel=0.1)
    b = write_synthetic_land_cover(tmp_path / "b.tif", np.full((5, 5), 40), west=116.5, north=6.0, pixel=0.1)
    r = process_land_cover([a, b], (116.0, 5.5, 117.0, 6.0), out_dir=tmp_path / "o")
    assert len(r.rasters) == 1 and r.rasters[0]["name"] == "land_cover.tif"
    with rasterio.open(r.rasters[0]["path"]) as s:
        assert s.width == 10 and set(np.unique(s.read(1))) == {10, 40}
