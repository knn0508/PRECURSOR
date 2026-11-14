import importlib
import os

from pyproj.datadir import get_data_dir

from app.core import geo_env


def test_overrides_foreign_proj_dir(monkeypatch):
    monkeypatch.setenv("PROJ_LIB", "C:/somewhere/else")
    monkeypatch.delenv("PROJ_DATA", raising=False)
    importlib.reload(geo_env)
    assert os.environ["PROJ_LIB"] == os.environ["PROJ_DATA"] == get_data_dir()
