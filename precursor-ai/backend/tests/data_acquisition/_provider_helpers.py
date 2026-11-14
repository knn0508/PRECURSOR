"""Shared test helpers for the CMR-backed providers (NASADEM / GPM / SMAP)."""
import json
from pathlib import Path
from types import SimpleNamespace

from shapely.geometry import box

from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.types import DownloadResult

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def settings(tmp_path, **kw):
    base = dict(data_root=tmp_path, max_file_size_bytes=3 * 1024**3, max_granules_per_request=10,
                gpm_resolution="daily", enable_smap=True, smap_collection="SPL3SMP_E")
    return SimpleNamespace(**{**base, **kw})


def aoi(w=44, s=40, e=45, n=41):
    return AOI.from_geometry("t", box(w, s, e, n))


class FakeAuth:
    def get_session(self):
        return "SESSION"


class FakeDM:
    def __init__(self):
        self.calls = []

    def download(self, url, dest, **kw):
        self.calls.append((url, dest, kw))
        return DownloadResult(path=dest, size_bytes=1, sha256="x")
