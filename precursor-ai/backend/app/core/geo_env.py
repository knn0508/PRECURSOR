"""Point GDAL/PROJ at pyproj's bundled data. Import before any geo library.

Some machines have PROJ_LIB set by another install (e.g. PostgreSQL's older proj.db), which breaks
rasterio CRS handling. Overriding with the pyproj directory is harmless where it is already correct.
"""
import os

from pyproj.datadir import get_data_dir

for _var in ("PROJ_DATA", "PROJ_LIB"):
    os.environ[_var] = get_data_dir()
