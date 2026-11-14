"""AOI POLYGON masking in the provider clip (SYNTHETIC class-id raster, not WorldCover data).

Statistics must be "of the AOI polygon", not "of its bounding box": cells whose centre lies outside the polygon are excluded.
"""
import numpy as np
import pytest
from shapely.geometry import Polygon, box

from app.services.environmental.land_cover.land_cover_processor import process_land_cover
from app.services.environmental.providers.synthetic import write_synthetic_land_cover

# 10x10 grid of 0.1-degree cells, class 10 in the left half and 40 in the right half.
IDS = np.where(np.arange(10)[None, :] < 5, 10, 40).astype("uint8") * np.ones((10, 1), dtype="uint8")


def _tif(tmp_path):
    return write_synthetic_land_cover(tmp_path / "lc.tif", IDS, west=116.0, north=6.0, pixel=0.1)


def test_bbox_tuple_counts_every_cell(tmp_path):
    r = process_land_cover([_tif(tmp_path)], (116.0, 5.0, 117.0, 6.0))
    assert r.total_pixels == 100 and r.valid_pixels == 100


def test_polygon_excludes_cells_outside_it(tmp_path):
    left_half = box(116.0, 5.0, 116.5, 6.0)  # exactly the class-10 half
    r = process_land_cover([_tif(tmp_path)], left_half)
    ids = {c["class_id"]: c for c in r.classes}
    assert set(ids) == {10} and ids[10]["percent"] == pytest.approx(100.0)
    assert r.valid_pixels == 50


def test_triangle_is_a_strict_subset_of_its_bbox(tmp_path):
    tri = Polygon([(116.0, 5.0), (117.0, 5.0), (116.0, 6.0)])  # lower-left triangle, ~half the bbox
    r = process_land_cover([_tif(tmp_path)], tri)
    assert 40 <= r.valid_pixels <= 60
    total = sum(c["percent"] for c in r.classes)
    assert total == pytest.approx(100.0)


def test_written_clip_has_polygon_mask_and_window_transform(tmp_path):
    import rasterio
    tri = Polygon([(116.0, 5.0), (117.0, 5.0), (116.0, 6.0)])
    r = process_land_cover([_tif(tmp_path)], tri, out_dir=tmp_path / "o")
    with rasterio.open(r.rasters[0]["path"]) as s:
        out = s.read(1)
        assert s.nodata == 0 and s.transform.a == pytest.approx(0.1)
    assert 0 < (out != 0).sum() == r.valid_pixels < 100
