"""M2 acquisition checks on REAL downloaded files (skipped when data/ml/raw/manifest.json is absent).
Integrity only; a passing check is not scientific validation."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/ml/raw"
MAN = RAW / "manifest.json"
PLAN = ROOT / "ml/reports/m2_probe/m2_plan.json"
pytestmark = pytest.mark.skipif(not MAN.exists() or not PLAN.exists(), reason="M2 data not present")
sys.path.insert(0, str(ROOT / "ml/scripts"))


def _manifest():
    return json.loads(MAN.read_text())


def test_manifest_completeness_vs_plan():
    plan = json.loads(PLAN.read_text())["items"]
    planned = {i["dest"] for i in plan if i.get("status") != "NOT_IN_CATALOG"}
    have = set(_manifest())
    assert have <= planned, "manifest has files that are not on the approved plan"
    missing = planned - have
    assert not missing, sorted(missing)[:5]  # every approved item arrived (SGMC replaced by the state files, user-approved)
    nasadem = [k for k in have if k.startswith("nasadem/")]
    wc = [k for k in have if k.startswith("worldcover/")]
    geo = [k for k in have if k.startswith("geology_state/")]
    imerg = [k for k in have if k.startswith("imerg_monthly/")]
    assert len(nasadem) == 27 and len(wc) == 8 and len(geo) == 3 and len(imerg) == 199


def test_checksums_and_sizes_match_manifest():
    for key, m in _manifest().items():
        p = RAW / key
        assert p.exists() and p.stat().st_size == m["size_bytes"], key
        h = hashlib.sha256()
        with p.open("rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                h.update(c)
        assert h.hexdigest() == m["sha256"], key
        assert m["url"] and "?" not in m["url"] and m["licence"] and m["retrieved_utc"]


def test_limits_respected():
    m = _manifest()
    assert sum(v["size_bytes"] for v in m.values()) < 30 * 10**9
    assert max(v["size_bytes"] for v in m.values()) < 2 * 10**9


def test_idempotent_rerun_skips_verified_files():
    sys.path.insert(0, str(ROOT / "backend"))
    pytest.importorskip("app.core.config")  # needs the backend venv (Phase 2 services, read-only)
    import m2_acquire as m2

    plan = json.loads(PLAN.read_text())["items"]
    done = [i for i in plan if i["dest"] in _manifest()]
    before = MAN.read_text()
    mtimes = {i["dest"]: (RAW / i["dest"]).stat().st_mtime_ns for i in done}
    assert m2.download(done) == 0  # no network: every item is verified and skipped
    assert MAN.read_text() == before
    assert all((RAW / k).stat().st_mtime_ns == v for k, v in mtimes.items())
