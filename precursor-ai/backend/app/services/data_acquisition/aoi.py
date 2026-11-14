"""Area of Interest: validated, EPSG:4326, Polygon/MultiPolygon only."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely import wkt
from shapely.errors import GeometryTypeError, ShapelyError
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.services.data_acquisition.types import AOIError

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class AOI:
    name: str
    geometry: BaseGeometry  # always EPSG:4326 (lon, lat)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(west, south, east, north)"""
        return tuple(self.geometry.bounds)  # type: ignore[return-value]

    @property
    def wkt(self) -> str:
        return self.geometry.wkt

    def validate_size(self, max_degrees: float) -> None:
        w, s, e, n = self.bbox
        if (e - w) > max_degrees or (n - s) > max_degrees:
            raise AOIError(
                f"AOI bounding box is {e - w:.2f} x {n - s:.2f} degrees; the limit is {max_degrees} degrees. "
                "Use a smaller AOI (the pipeline never bulk-downloads whole countries)."
            )

    # ---- constructors ---------------------------------------------------------------
    @classmethod
    def from_geometry(cls, name: str, geom: BaseGeometry, crs: str = WGS84) -> "AOI":
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise AOIError(f"AOI must be a Polygon or MultiPolygon, got {geom.geom_type}")
        try:
            src = CRS.from_user_input(crs)
        except Exception as exc:  # pyproj raises several types
            raise AOIError(f"Unknown CRS {crs!r}") from exc
        if not src.equals(CRS.from_user_input(WGS84)):
            geom = transform(Transformer.from_crs(src, WGS84, always_xy=True).transform, geom)
        if geom.is_empty:
            raise AOIError("AOI geometry is empty")
        if not geom.is_valid:
            raise AOIError("AOI geometry is topologically invalid (self-intersection or bad ring)")
        w, s, e, n = geom.bounds
        if not (-180 <= w and e <= 180 and -90 <= s and n <= 90):
            raise AOIError("AOI coordinates are outside lon/lat bounds (check the axis order and CRS)")
        return cls(name=name, geometry=geom)

    @classmethod
    def from_geojson(cls, name: str, data: dict[str, Any], crs: str = WGS84) -> "AOI":
        """Accepts a Geometry, a Feature, or a FeatureCollection (all features are unioned)."""
        try:
            kind = data.get("type")
            if kind == "FeatureCollection":
                from shapely.ops import unary_union

                geoms = [shape(f["geometry"]) for f in data.get("features", [])]
                if not geoms:
                    raise AOIError("FeatureCollection has no features")
                geom = unary_union(geoms)
            elif kind == "Feature":
                geom = shape(data["geometry"])
            else:
                geom = shape(data)
        except (GeometryTypeError, ShapelyError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AOIError(f"Invalid GeoJSON: {exc}") from exc
        return cls.from_geometry(name, geom, crs)

    @classmethod
    def from_wkt(cls, name: str, text: str, crs: str = WGS84) -> "AOI":
        try:
            geom = wkt.loads(text)
        except (ShapelyError, ValueError) as exc:
            raise AOIError(f"Invalid WKT: {exc}") from exc
        return cls.from_geometry(name, geom, crs)

    @classmethod
    def from_file(cls, path: str | Path, name: str | None = None, crs: str = WGS84) -> "AOI":
        p = Path(path)
        if not p.is_file():
            raise AOIError(f"AOI file not found: {p}")
        text = p.read_text(encoding="utf-8")
        label = name or p.stem
        if p.suffix.lower() in (".wkt", ".txt"):
            return cls.from_wkt(label, text, crs)
        try:
            return cls.from_geojson(label, json.loads(text), crs)
        except json.JSONDecodeError as exc:
            raise AOIError(f"{p.name} is not valid JSON/GeoJSON: {exc}") from exc
