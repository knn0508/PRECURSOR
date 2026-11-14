"""Provider proposal/describe tests. Fake session asserts ZERO requests; fixtures are SYNTHETIC."""
from datetime import UTC, datetime

import numpy as np

from app.services.environmental.providers.land_cover import LandCoverProvider, tile_count
from app.services.environmental.providers.soilgrids import SoilGridsProvider
from app.services.environmental.providers.synthetic import write_synthetic_land_cover, write_synthetic_soil
from app.services.environmental.providers.usgs_earthquake import USGSEarthquakeProvider

BB = (116.0, 5.5, 116.5, 6.0)


class NoCalls:
    calls = 0

    def get(self, *a, **k):
        NoCalls.calls += 1
        raise AssertionError("network used")


def test_plans_are_proposals_without_requests():
    s = NoCalls()
    usgs = USGSEarthquakeProvider()
    for p in (SoilGridsProvider(), LandCoverProvider(), usgs):
        assert p.describe()["implementation_status"]
        prop = p.plan_acquisition(BB, start=datetime(2020, 1, 1, tzinfo=UTC))
        assert prop.status == "PROPOSAL_ONLY_NOT_DOWNLOADED" and prop.requires_auth is False and prop.source_urls
    assert NoCalls.calls == 0 and s is not None


def test_soil_proposal_counts_layers_and_land_cover_tiles():
    sp = SoilGridsProvider().plan_acquisition(BB, properties=("clay", "sand"), statistics=("mean",))
    assert sp.expected_file_count == 2 * 6 and sp.estimated_size_mb > 0 and "ESTIMATE" in sp.size_basis
    assert tile_count((116.0, 5.5, 116.5, 6.0)) == 1 and tile_count((113.0, 5.0, 117.0, 7.0)) == 4  # 3-degree tiles
    assert LandCoverProvider().plan_acquisition(BB).version.startswith("v200")


def test_local_inputs_only_files_covering_aoi(tmp_path):
    d = tmp_path / "external" / "soilgrids"
    d.mkdir(parents=True)
    arr = np.full((4, 4), 100)
    write_synthetic_soil(d, "clay", 0, 5, "mean", arr, west=116.0, north=6.0, pixel=0.1)
    write_synthetic_soil(d, "sand", 0, 5, "mean", arr, west=10.0, north=6.0, pixel=0.1)  # elsewhere
    (d / "notes.tif").write_bytes(b"x")
    assert [p.name for p in SoilGridsProvider().local_inputs(tmp_path, BB)] == ["clay_0-5cm_mean.tif"]
    assert LandCoverProvider().local_inputs(tmp_path, BB) == []
    d2 = tmp_path / "external" / "land_cover"
    d2.mkdir()
    write_synthetic_land_cover(d2 / "lc.tif", np.full((4, 4), 10), west=116.0, north=6.0, pixel=0.1)
    assert len(LandCoverProvider().local_inputs(tmp_path, BB)) == 1
