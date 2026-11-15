"""Production default refuses synthetic-tagged inputs; the real NASADEM-derived path is unaffected."""
import pytest

from app.core.config import Settings, get_settings
from app.core.synthetic_guard import refuse_if_synthetic
from app.services.environmental.types import EnvError


def test_default_refuses_synthetic(monkeypatch):
    monkeypatch.delenv("ALLOW_SYNTHETIC_INPUTS", raising=False)
    get_settings.cache_clear()
    assert Settings(_env_file=None).allow_synthetic_inputs is False
    with pytest.raises(EnvError, match="Real data only"):
        refuse_if_synthetic(True, EnvError, "x.tif")
    refuse_if_synthetic(False, EnvError, "real.tif")            # real files pass


def test_flag_allows_for_tests(monkeypatch):
    monkeypatch.setenv("ALLOW_SYNTHETIC_INPUTS", "true")
    get_settings.cache_clear()
    refuse_if_synthetic(True, EnvError, "x.tif")


def test_synthetic_raster_is_rejected_end_to_end(tmp_path, monkeypatch):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from app.services.environmental.raster.io import inspect_raster
    from app.services.environmental.types import SYNTHETIC_TAG
    p = tmp_path / "s.tif"
    with rasterio.open(p, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(0, 1, .25, .25)) as d:
        d.write(np.ones((1, 4, 4), "float32")); d.update_tags(**{SYNTHETIC_TAG: "1"})
    monkeypatch.setenv("ALLOW_SYNTHETIC_INPUTS", "false")
    get_settings.cache_clear()
    with pytest.raises(EnvError, match="synthetic"):
        inspect_raster(p)
    monkeypatch.setenv("ALLOW_SYNTHETIC_INPUTS", "true")
    get_settings.cache_clear()
    assert inspect_raster(p).is_synthetic is True
