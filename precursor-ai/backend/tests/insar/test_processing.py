"""GUNW processing on SYNTHETIC data: numerical oracles, nodata handling, memory-bounded blocks, immutability."""
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio

from app.services.insar import storage, synthetic
from app.services.insar.external import ExternalTool
from app.services.insar.inspection import inspect_product
from app.services.insar.processing import Cancelled, process_gunw, quality_report
from app.services.insar.types import BlockedMissingInput, ProcessingConfig, ProcessingError, ProductType


def run(tmp_path, f, cfg=None, **kw):
    rep = inspect_product(f)
    out = {k: tmp_path / "out" / k.value for k in ProductType}
    for d in out.values():
        d.mkdir(parents=True)
    res = process_gunw(f, rep, cfg or ProcessingConfig(), out_dirs=out, tmp_dir=tmp_path / "tmp", min_free_bytes=0, **kw)
    return rep, res


def read(res, kind):
    o = next(o for o in res.outputs if o.kind is kind)
    with rasterio.open(o.path) as ds:
        return ds.read(1), ds.tags(), ds


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_displacement_equals_independent_oracle(tmp_path):
    phase = np.linspace(-6, 6, 40 * 48, dtype="float32").reshape(40, 48)
    f = synthetic.make_gunw(tmp_path / "g.h5", phase=phase, fill_value=None)
    _, res = run(tmp_path, f)
    d, tags, ds = read(res, ProductType.LOS_DISPLACEMENT)
    assert d == pytest.approx(synthetic.expected_displacement_mm(phase), abs=1e-4)
    assert tags["UNITS"] == "mm" and tags["DATA_ORIGIN"] == "SYNTHETIC_FIXTURE"
    assert tags["SCIENTIFICALLY_VALIDATED"] == "false" and tags["SIGN_CONVENTION_VERIFIED"] == "false"
    with rasterio.open(next(o.path for o in res.outputs if o.kind is ProductType.LOS_DISPLACEMENT)) as ds:
        assert ds.crs.to_epsg() == 32618 and ds.transform.a == 80.0 and ds.transform.e == -80.0
        assert np.isnan(ds.nodata)


def test_fill_and_nan_become_nodata_never_zero(tmp_path):
    phase = np.full((40, 48), 1.0, dtype="float32")
    phase[3, 3], phase[4, 4] = -9999.0, np.nan
    f = synthetic.make_gunw(tmp_path / "g.h5", phase=phase)
    _, res = run(tmp_path, f)
    d = read(res, ProductType.LOS_DISPLACEMENT)[0]
    assert np.isnan(d[3, 3]) and np.isnan(d[4, 4])
    assert (d[np.isfinite(d)] != 0).all()
    s = res.stats["displacement"]
    assert s["nodata_pixels"] == 2 and s["valid_pixels"] == 40 * 48 - 2
    assert s["nodata_percent"] == pytest.approx(100 * 2 / (40 * 48))


def test_block_size_does_not_change_result(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5", width=50, height=37)
    _, a = run(tmp_path / "a", f, ProcessingConfig(block_rows=7))
    _, b = run(tmp_path / "b", f, ProcessingConfig(block_rows=4096))
    da, db_ = read(a, ProductType.LOS_DISPLACEMENT)[0], read(b, ProductType.LOS_DISPLACEMENT)[0]
    assert np.array_equal(da, db_, equal_nan=True)
    assert a.stats["displacement"]["mean"] == pytest.approx(b.stats["displacement"]["mean"])


def test_coherence_raster_is_preserved_and_threshold_masks_displacement_only(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")  # first width//8 = 6 columns have coherence 0.2, rest 0.8
    _, res = run(tmp_path, f, ProcessingConfig(coherence_threshold=0.5))
    c = read(res, ProductType.COHERENCE)[0]
    d = read(res, ProductType.LOS_DISPLACEMENT)[0]
    assert np.allclose(c[:, :6], 0.2) and np.allclose(c[:, 6:], 0.8)  # original values untouched by the threshold
    assert np.isnan(d[:, :6]).all() and np.isfinite(d[:, 6:]).all()  # low-coherence pixels are missing, not zero
    assert res.stats["masked_by_coherence_threshold"] == 6 * 40
    assert res.stats["coherence"]["fraction_below_threshold"] == pytest.approx(6 / 48)


def test_default_has_no_coherence_threshold(tmp_path):
    _, res = run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5"))
    d = read(res, ProductType.LOS_DISPLACEMENT)[0]
    assert np.isfinite(d).sum() == res.stats["displacement"]["valid_pixels"] == 40 * 48
    assert res.stats["masked_by_coherence_threshold"] == 0


def test_velocity_uses_temporal_baseline(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    _, res = run(tmp_path, f)
    d = read(res, ProductType.LOS_DISPLACEMENT)[0]
    v, vtags, _ = read(res, ProductType.LOS_VELOCITY)
    assert v == pytest.approx(d / (12 / 365.25), rel=1e-5, abs=1e-3)
    assert vtags["UNITS"] == "mm/year" and res.stats["temporal_baseline_days"] == 12


def test_velocity_skipped_with_warning_when_dates_invalid(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5", ref="2025-10-13T12:00:00", sec="2025-10-01T12:00:00")
    _, res = run(tmp_path, f)
    assert not any(o.kind is ProductType.LOS_VELOCITY for o in res.outputs)
    assert any("velocity not computed" in w for w in res.warnings)
    assert res.stats["velocity"] is None


def test_outputs_are_cogs_with_provenance_extras(tmp_path):
    _, res = run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5", width=600, height=520))
    o = next(o for o in res.outputs if o.kind is ProductType.LOS_DISPLACEMENT)
    with rasterio.open(o.path) as ds:
        assert ds.profile["tiled"] and ds.overviews(1)  # COG: tiled + overviews
        assert "LAYOUT=COG" in str(ds.tags(ns="IMAGE_STRUCTURE")) or ds.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"
    assert len(o.extra["bounds_4326"]) == 4
    assert not list((tmp_path / "tmp").glob("*.tmp.tif"))  # intermediates cleaned up


def test_keep_intermediates(tmp_path):
    run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5"), ProcessingConfig(keep_intermediates=True))
    assert list((tmp_path / "tmp").glob("*.tmp.tif"))


def test_input_file_is_never_modified(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    before = sha(f)
    run(tmp_path, f)
    assert sha(f) == before


def test_requires_supported_displacement(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5", with_frequency=False)
    with pytest.raises(ProcessingError, match="not supported"):
        run(tmp_path, f)


def test_all_invalid_pixels_fails_loudly(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5", phase=np.full((40, 48), np.nan, dtype="float32"))
    with pytest.raises(ProcessingError, match="no valid displacement"):
        run(tmp_path, f)


def test_unknown_polarization_is_an_error(tmp_path):
    with pytest.raises(ProcessingError, match="polarization"):
        run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5"), ProcessingConfig(polarization="VV"))


def test_cancellation_stops_processing(tmp_path):
    with pytest.raises(Cancelled):
        run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5"), cancelled=lambda: True)


def test_insufficient_disk_is_reported(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    rep = inspect_product(f)
    out = {k: tmp_path / k.value for k in ProductType}
    with pytest.raises(ProcessingError, match="insufficient disk"):
        process_gunw(f, rep, ProcessingConfig(), out_dirs=out, tmp_dir=tmp_path / "t", min_free_bytes=10**18)


def test_quality_report_labels_and_never_claims_validation(tmp_path):
    rep, res = run(tmp_path, synthetic.make_gunw(tmp_path / "g.h5"))
    now = datetime.now(UTC)
    q = quality_report(rep=rep, cfg=ProcessingConfig(), result=res, status="COMPLETED", started=now, ended=now,
                       input_ref="g.h5", errors=[])
    assert q["data_origin"] == "SYNTHETIC_FIXTURE" and "SYNTHETIC" in q["label"]
    assert q["real_satellite_data"] is False and q["real_data_validation"] == "NOT_PERFORMED"
    assert q["scientifically_validated"] is False and q["sign_convention_verified"] is False
    assert q["input"]["crs"] == "EPSG:32618" and q["input"]["wavelength_m"] == pytest.approx(0.2384, abs=1e-4)
    assert q["statistics"]["displacement"]["unit"] == "mm"
    assert {"python", "numpy", "h5py", "rasterio", "gdal"} <= set(q["software"])
    assert any("risk map" in x for x in q["limitations"])


def test_quality_report_for_failed_run_without_inspection():
    now = datetime.now(UTC)
    q = quality_report(rep=None, cfg=ProcessingConfig(), result=None, status="FAILED", started=now, ended=now,
                       input_ref="x", errors=["boom"])
    assert q["errors"] == ["boom"] and q["input"] is None and q["real_data_validation"] == "NOT_PERFORMED"


# --- storage safety ---------------------------------------------------------------------------------
def test_storage_blocks_traversal(tmp_path):
    storage.ensure_layout(tmp_path)
    for bad in ("../x.h5", "a/b.h5", "..", "", ".hidden"):
        with pytest.raises(ValueError):
            storage.resolve_sample(tmp_path, bad)
    with pytest.raises(FileNotFoundError):
        storage.resolve_sample(tmp_path, "missing.h5")
    with pytest.raises(ProcessingError):
        storage.resolve_output(tmp_path, "../../etc/passwd")
    with pytest.raises(ProcessingError):
        storage.resolve_output(tmp_path, "raw/nisar/gunw/x.h5")  # raw data is not an output
    (tmp_path / "raw").mkdir()
    with pytest.raises(ProcessingError):
        storage.resolve_acquisition_file(tmp_path, str(tmp_path / "samples" / "x.h5"))


# --- external tool gate ---------------------------------------------------------------------------------
def test_external_tool_availability_version_run_and_errors(tmp_path):
    py = ExternalTool("python", (Path(sys.executable).name, sys.executable), ("--version",))
    assert py.available() and "Python" in py.version()
    out = tmp_path / "o.txt"
    py.run(["-c", f"open({str(out)!r},'w').write('x')"], timeout=30, expected_outputs=[out])
    with pytest.raises(ProcessingError, match="exited with code 3"):
        py.run(["-c", "import sys; sys.exit(3)"], timeout=30)
    with pytest.raises(ProcessingError, match="timed out"):
        py.run(["-c", "import time; time.sleep(5)"], timeout=1)
    with pytest.raises(ProcessingError, match="expected output is missing"):
        py.run(["-c", "pass"], timeout=30, expected_outputs=[tmp_path / "never.txt"])
    ghost = ExternalTool("ghost", ("definitely-not-installed-xyz",))
    assert not ghost.available() and ghost.version() is None
    with pytest.raises(BlockedMissingInput):
        ghost.require()


def test_sentinel1_process_is_blocked_here():
    from app.services.insar.adapters.sentinel1_slc import Sentinel1SLCAdapter

    with pytest.raises(BlockedMissingInput, match="not available"):
        Sentinel1SLCAdapter().process()
