"""Synthetic GUNW-like fixtures for tests and demos. EVERYTHING here is fake and says so.

The layout mimics what the NISAR GUNW spec is believed to contain (`/science/LSAR/GUNW/grids/frequencyA/
unwrappedInterferogram/<pol>/...`) but it has NOT been checked against a real granule. A file produced here carries
the root attribute `precursor_synthetic_fixture`, which the inspector turns into data_origin=SYNTHETIC_FIXTURE.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from app.services.insar.hdf import SYNTHETIC_MARKER
from app.services.insar.phase_to_displacement import SPEED_OF_LIGHT_M_S

L_BAND_HZ = 1_257_500_000.0  # nominal L-band centre frequency used only to make a plausible wavelength


def expected_displacement_mm(phase: np.ndarray, frequency_hz: float = L_BAND_HZ) -> np.ndarray:
    """Independent restatement of the conversion for test oracles."""
    lam = SPEED_OF_LIGHT_M_S / frequency_hz
    return -(lam / (4 * np.pi)) * phase * 1000.0


def make_gunw(
    path: Path, *, width: int = 48, height: int = 40, epsg: int = 32618, spacing: float = 80.0,
    ref: str = "2025-10-01T12:00:00.000000", sec: str = "2025-10-13T12:00:00.000000",
    pols: tuple[str, ...] = ("HH",), units: str | None = "radians", with_coherence: bool = True,
    with_frequency: bool = True, with_coords: bool = True, phase: np.ndarray | None = None,
    coherence: np.ndarray | None = None, fill_value: float | None = -9999.0, orbit: str = "Ascending",
    product_type: str = "GUNW",
) -> Path:
    """A SYNTHETIC unwrapped-interferogram file: a smooth Gaussian bump of phase, so expected values are known."""
    yy, xx = np.mgrid[0:height, 0:width]
    if phase is None:
        phase = (6.0 * np.exp(-(((xx - width / 2) / (width / 6)) ** 2 + ((yy - height / 2) / (height / 6)) ** 2))).astype("float32")
    if coherence is None:
        coherence = np.full((height, width), 0.8, dtype="float32")
        coherence[:, : width // 8] = 0.2  # a deliberately low-coherence strip
    x = 500_000.0 + spacing * np.arange(width)
    y = 4_000_000.0 - spacing * np.arange(height)
    with h5py.File(path, "w") as f:
        f.attrs[SYNTHETIC_MARKER] = "SYNTHETIC TEST DATA: not a satellite observation"
        ident = f.create_group("science/LSAR/identification")
        ident["productType"] = product_type
        ident["productVersion"] = "0.0-synthetic"
        ident["orbitPassDirection"] = orbit
        ident["trackNumber"] = np.int32(1)
        ident["referenceZeroDopplerStartTime"] = ref
        ident["secondaryZeroDopplerStartTime"] = sec
        grp = f.create_group("science/LSAR/GUNW/grids/frequencyA")
        if with_frequency:
            grp["centerFrequency"] = L_BAND_HZ
        for pol in pols:
            g = grp.create_group(f"unwrappedInterferogram/{pol}")
            d = g.create_dataset("unwrappedPhase", data=phase, chunks=(16, 16))
            if units:
                d.attrs["units"] = units
            if fill_value is not None:
                d.attrs["_FillValue"] = fill_value
            if with_coherence:
                g.create_dataset("coherenceMagnitude", data=coherence, chunks=(16, 16))
            g.create_dataset("connectedComponents", data=np.ones((height, width), dtype="uint16"))
        ug = grp["unwrappedInterferogram"]
        if with_coords:
            ug["xCoordinates"] = x
            ug["yCoordinates"] = y
            p = ug.create_dataset("projection", data=np.int32(epsg))
            p.attrs["epsg_code"] = epsg
        f.create_group("science/LSAR/GUNW/metadata/radarGrid")["perpendicularBaseline"] = np.float32(120.0)
    return path


def make_gslc(path: Path, *, width: int = 32, height: int = 24, epsg: int = 32618) -> Path:
    """SYNTHETIC complex single-date raster (unit-amplitude with a phase ramp)."""
    yy, xx = np.mgrid[0:height, 0:width]
    slc = np.exp(1j * 0.1 * xx).astype("complex64")
    with h5py.File(path, "w") as f:
        f.attrs[SYNTHETIC_MARKER] = "SYNTHETIC TEST DATA: not a satellite observation"
        i = f.create_group("science/LSAR/identification")
        i["productType"] = "GSLC"
        i["productVersion"] = "0.0-synthetic"
        i["orbitPassDirection"] = "Descending"
        i["zeroDopplerStartTime"] = "2025-10-01T12:00:00.000000"
        g = f.create_group("science/LSAR/GSLC/grids/frequencyA")
        g["centerFrequency"] = L_BAND_HZ
        g["xCoordinates"] = 500_000.0 + 5.0 * np.arange(width)
        g["yCoordinates"] = 4_000_000.0 - 5.0 * np.arange(height)
        g["projection"] = np.int32(epsg)
        g.create_dataset("HH", data=slc)
    return path


def make_gcov(path: Path, *, width: int = 32, height: int = 24, epsg: int = 32618) -> Path:
    """SYNTHETIC covariance (backscatter power) raster."""
    with h5py.File(path, "w") as f:
        f.attrs[SYNTHETIC_MARKER] = "SYNTHETIC TEST DATA: not a satellite observation"
        i = f.create_group("science/LSAR/identification")
        i["productType"] = "GCOV"
        i["productVersion"] = "0.0-synthetic"
        i["orbitPassDirection"] = "Ascending"
        i["zeroDopplerStartTime"] = "2025-10-01T12:00:00.000000"
        g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        g["xCoordinates"] = 500_000.0 + 10.0 * np.arange(width)
        g["yCoordinates"] = 4_000_000.0 - 10.0 * np.arange(height)
        g["projection"] = np.int32(epsg)
        for term in ("HHHH", "HVHV"):
            g.create_dataset(term, data=np.full((height, width), 0.05, dtype="float32"))
    return path
