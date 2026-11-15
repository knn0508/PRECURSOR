"""Static terrain (Copernicus GLO-30 DEM, public AWS) and GPM IMERG daily rainfall."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd


def cop_dem_url(lat: float, lon: float) -> str:
    la, lo = math.floor(lat), math.floor(lon)
    ns, ew = ("N" if la >= 0 else "S"), ("E" if lo >= 0 else "W")
    tile = f"Copernicus_DSM_COG_10_{ns}{abs(la):02d}_00_{ew}{abs(lo):03d}_00_DEM"
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif"


def dem_on_grid(x: np.ndarray, y: np.ndarray, crs_wkt: str, aoi) -> dict:
    """Reproject Copernicus DEM (public, no login) onto the OPERA grid and derive terrain."""
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_origin

    url = cop_dem_url(*aoi.center[::-1])
    dx, dy = float(abs(x[1] - x[0])), float(abs(y[1] - y[0]))
    dst_tr = from_origin(x.min() - dx / 2, y.max() + dy / 2, dx, dy)
    elev = np.full((len(y), len(x)), np.nan, np.float32)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(f"/vsicurl/{url}") as src:
            reproject(rasterio.band(src, 1), elev, dst_transform=dst_tr, dst_crs=crs_wkt,
                      resampling=Resampling.bilinear, dst_nodata=np.nan)
    if y[0] < y[-1]:  # grid stored south-up
        elev = elev[::-1]
    gy, gx = np.gradient(elev, dy, dx)  # metric CRS => metres
    if y[0] > y[-1]:
        gy = -gy  # row index increases southward
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    aspect = np.arctan2(-gx, -gy)  # downslope direction, radians from north
    lap = (np.gradient(np.gradient(elev, dy, axis=0), dy, axis=0)
           + np.gradient(np.gradient(elev, dx, axis=1), dx, axis=1))  # direction-invariant
    return {"elevation": elev, "slope_deg": slope, "aspect_sin": np.sin(aspect),
            "aspect_cos": np.cos(aspect), "curvature": -lap, "source": url}


def imerg_daily_point(lat: float, lon: float, start: str, end: str, cache: Path,
                      short_name: str = "GPM_3IMERGDF", version: str = "07", workers: int = 16) -> pd.Series:
    """Daily precipitation (mm/day) at the IMERG cell containing (lat, lon). Cached to CSV."""
    import earthaccess
    import xarray as xr

    if cache.exists():
        s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0]
        if s.index.min() <= pd.Timestamp(start) and s.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=3):
            return s
    res = earthaccess.search_data(short_name=short_name, version=version, temporal=(start, end),
                                  bounding_box=(lon - .05, lat - .05, lon + .05, lat + .05))
    from .remote import RangeFS
    fs = RangeFS()

    def one(g):
        url = next(u for u in g.data_links() if u.endswith((".nc4", ".nc")))
        with fs.open(url) as f:
            ds = xr.open_dataset(f, engine="h5netcdf")
            var = "precipitation" if "precipitation" in ds else "precipitationCal"
            v = ds[var].sel(lat=lat, lon=lon, method="nearest").squeeze()
            t = pd.Timestamp(pd.to_datetime(ds["time"].values).ravel()[0]).normalize()
            val, units = float(v.values), ds[var].attrs.get("units", "")
            ds.close()
        return t, val, units

    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(one, res))
    units = {u for _, _, u in out}
    s = pd.Series({t: v for t, v, _ in out}).sort_index()
    s.name = f"{short_name}_v{version}_mm_per_day"
    if not all(("mm" in u) for u in units):
        raise ValueError(f"unexpected IMERG units {units}")
    if any("hr" in u for u in units):  # daily product stores mm/day in V07; guard anyway
        raise ValueError(f"IMERG units look hourly: {units}; convert explicitly")
    cache.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(cache)
    return s
