"""Inspection and adapters, on SYNTHETIC fixtures (layout believed to match NISAR; not verified against a real file)."""
import h5py
import numpy as np
import pytest

from app.services.insar import synthetic
from app.services.insar.inspection import detect_kind, inspect_product
from app.services.insar.types import DataOrigin, ProductKind


def test_gunw_inspection_roles_grid_and_metadata(tmp_path):
    rep = inspect_product(synthetic.make_gunw(tmp_path / "g.h5"))
    assert rep.product_kind is ProductKind.GUNW and rep.file_format == "hdf5"
    assert rep.data_origin is DataOrigin.SYNTHETIC_FIXTURE
    assert any("SYNTHETIC" in w for w in rep.warnings)
    assert rep.roles["unwrapped_phase"].endswith("/HH/unwrappedPhase") and rep.roles["coherence"].endswith("coherenceMagnitude")
    assert rep.grid.epsg == 32618 and (rep.grid.width, rep.grid.height) == (48, 40)
    assert rep.grid.dx == 80.0 and rep.grid.dy == -80.0
    assert rep.wavelength_m == pytest.approx(0.2384, abs=1e-4)
    assert rep.orbit_direction == "Ascending" and rep.product_version == "0.0-synthetic"
    assert (rep.secondary_time - rep.reference_time).days == 12
    assert rep.displacement_supported and not rep.displacement_blockers
    assert "DISPLACEMENT_CALCULATION" in rep.supported_stages
    assert any("NOT verified" in w for w in rep.warnings)  # sign convention caveat always present
    assert rep.to_dict()["product_kind"] == "GUNW"


def test_unmarked_file_keeps_given_origin(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    with h5py.File(f, "a") as h:
        del h.attrs["precursor_synthetic_fixture"]
    assert inspect_product(f, DataOrigin.REAL_SATELLITE).data_origin is DataOrigin.REAL_SATELLITE


@pytest.mark.parametrize("kw,needle", [
    (dict(with_frequency=False), "frequency"),
    (dict(units="degrees"), "not radians"),
    (dict(with_coords=False), "coordinate"),
])
def test_gunw_blockers_disable_displacement(tmp_path, kw, needle):
    rep = inspect_product(synthetic.make_gunw(tmp_path / "g.h5", **kw))
    assert not rep.displacement_supported
    assert any(needle in b for b in rep.displacement_blockers)
    assert "DISPLACEMENT_CALCULATION" not in rep.supported_stages


def test_gunw_missing_units_and_coherence_are_warnings_not_blockers(tmp_path):
    rep = inspect_product(synthetic.make_gunw(tmp_path / "g.h5", units=None, with_coherence=False))
    assert rep.displacement_supported
    assert any("no 'units'" in w for w in rep.warnings) and any("no coherenceMagnitude" in w for w in rep.warnings)
    assert "coherence" not in rep.roles


def test_gunw_multi_polarization_is_reported(tmp_path):
    rep = inspect_product(synthetic.make_gunw(tmp_path / "g.h5", pols=("HH", "HV")))
    assert rep.metadata["polarizations"] == ["HH", "HV"]
    assert any("several polarizations" in w for w in rep.warnings)


def test_gunw_without_unwrapped_phase(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    with h5py.File(f, "a") as h:
        del h["science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase"]
    rep = inspect_product(f)
    assert "unwrappedPhase" in rep.missing and not rep.displacement_supported


def test_missing_identification_is_reported(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    with h5py.File(f, "a") as h:
        del h["science/LSAR/identification/orbitPassDirection"]
    rep = inspect_product(f)
    assert "identification/orbitPassDirection" in rep.missing


def test_product_type_mismatch_warns(tmp_path):
    rep = inspect_product(synthetic.make_gunw(tmp_path / "g.h5", product_type="GCOV"))
    assert rep.product_kind is ProductKind.GUNW and any("productType" in w for w in rep.warnings)


def test_gslc_is_inspection_only_and_never_displacement(tmp_path):
    rep = inspect_product(synthetic.make_gslc(tmp_path / "s.h5"))
    assert rep.product_kind is ProductKind.GSLC
    assert "complex_HH" in rep.roles and rep.grid is not None
    assert not rep.displacement_supported and "DISPLACEMENT_CALCULATION" not in rep.supported_stages
    assert any("single-date" in b for b in rep.displacement_blockers)


def test_gcov_is_not_an_interferogram(tmp_path):
    rep = inspect_product(synthetic.make_gcov(tmp_path / "c.h5"))
    assert rep.product_kind is ProductKind.GCOV
    assert rep.metadata["covariance_terms"] == ["HHHH", "HVHV"] and rep.metadata["polarizations"] == ["HH", "HV"]
    assert not rep.displacement_supported
    assert "not interferometric phase" in rep.displacement_blockers[0]


def test_sentinel1_name_is_recognised_without_processing(tmp_path):
    name = "S1A_IW_SLC__1SDV_20240101T120000_20240101T120027_051234_063ABC_1234.zip"
    f = tmp_path / name
    import zipfile

    with zipfile.ZipFile(f, "w") as z:
        z.writestr("X.SAFE/manifest.safe", "<x/>")
        z.writestr("X.SAFE/measurement/a.tiff", "x")
    rep = inspect_product(f)
    assert rep.product_kind is ProductKind.S1_SLC and rep.file_format == "zip"
    assert rep.metadata["mission"] == "S1A" and rep.metadata["measurement_files"] == 1
    assert rep.reference_time.year == 2024 and not rep.displacement_supported
    assert rep.supported_stages == ["INSPECTING"]


def test_unrecognised_and_missing_files(tmp_path):
    junk = tmp_path / "x.bin"
    junk.write_bytes(b"not a sar file")
    rep = inspect_product(junk)
    assert rep.product_kind is ProductKind.UNKNOWN and not rep.displacement_supported
    other = tmp_path / "o.h5"
    with h5py.File(other, "w") as h:
        h["a"] = np.arange(3)
    assert detect_kind(other)[0] is ProductKind.UNKNOWN
    with pytest.raises(FileNotFoundError):
        inspect_product(tmp_path / "nope.h5")


def test_irregular_grid_is_rejected(tmp_path):
    f = synthetic.make_gunw(tmp_path / "g.h5")
    with h5py.File(f, "a") as h:
        p = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/xCoordinates"
        x = h[p][()]
        x[5] += 30
        h[p][...] = x
    rep = inspect_product(f)
    assert not rep.displacement_supported and any("irregular" in b for b in rep.displacement_blockers)
