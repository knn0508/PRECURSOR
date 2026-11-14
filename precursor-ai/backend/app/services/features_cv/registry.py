"""FeatureExtractor protocol, the registry and the built-in extractors (terrain, texture, change).

An extractor declares the Phase 4 layer types it needs and returns FeatureResults (an array plus its FeatureSpec) or a
list of skipped items with a reason. Nothing here scores or classifies: results are descriptive rasters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np
from affine import Affine

from app.services.environmental.dem.slope import cell_sizes_m, slope_degrees, terrain_gradients
from app.services.features_cv import change, terrain, texture
from app.services.features_cv.tiling import tiled_apply
from app.services.features_cv.types import (
    ChangeDetectionRefused, FeatureError, FeatureSpec, forbidden_names)

# Fixed quantisation bounds for layers whose range is physically defined (AOI independent => comparable across AOIs).
FIXED_BOUNDS = {"SLOPE": (0.0, 90.0), "NDVI": (-1.0, 1.0)}

DEFAULT_PARAMS: dict[str, Any] = {
    "relief_window_px": 5, "curvature_sigma_px": 1.0, "lineament_window_px": 15, "lineament_azimuths": [0.0, 45.0, 90.0, 135.0, 225.0, 315.0],
    "lineament_altitude_deg": 45.0, "canny_sigma": 1.0, "canny_low": 0.02, "canny_high": 0.06, "min_valid_fraction": 0.5,
    "texture_layers": ["SLOPE", "NDVI"], "texture_window_px": 16, "texture_levels": 16, "tile_px": 512,
}


@dataclass
class ExtractionContext:
    arrays: dict[str, np.ndarray]  # Phase 4 layer type -> array on the reference grid (NaN = missing)
    layers: dict[str, dict[str, Any]]  # Phase 4 layer type -> manifest entry
    grid: dict[str, Any]  # crs, transform (6), width, height, resolution_m
    params: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    change_inputs: dict[str, list[change.DatedInput]] = field(default_factory=dict)

    @property
    def res_m(self) -> float:
        return float(self.grid["resolution_m"])

    @property
    def transform(self) -> Affine:
        return Affine(*self.grid["transform"][:6])


@dataclass
class FeatureResult:
    spec: FeatureSpec
    array: np.ndarray
    transform: Affine  # the reference transform, or a block-grid transform for texture
    on_reference_grid: bool = True
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FeatureExtractor(Protocol):
    name: str

    def catalogue(self, params: dict[str, Any]) -> list[FeatureSpec]: ...  # static schema, no data needed
    def extract(self, ctx: ExtractionContext) -> tuple[list[FeatureResult], list[dict[str, str]]]: ...


def _skip(feature: str, reason: str) -> dict[str, str]:
    return {"feature": feature, "status": "NOT_AVAILABLE", "reason": reason}


def _p(params: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_PARAMS, **params}


def _sigma_tag(s: float) -> str:
    return f"{s:g}".replace(".", "p")


class TerrainExtractor:
    name = "terrain"

    def catalogue(self, params: dict[str, Any]) -> list[FeatureSpec]:
        p = _p(params)
        rw, lw, sg = p["relief_window_px"], p["lineament_window_px"], p["curvature_sigma_px"]
        return [
            FeatureSpec(f"local_relief_w{rw}", "terrain", "max - min elevation in the window", "m", window_px=rw, source_layers=["ELEVATION"], parameters={"min_valid_fraction": p["min_valid_fraction"]}),
            FeatureSpec("terrain_ruggedness_index", "terrain", "Riley (1999) TRI over the 3x3 neighbourhood", "m", window_px=3, source_layers=["ELEVATION"]),
            FeatureSpec(f"curvature_laplacian_s{_sigma_tag(sg)}", "terrain", "Laplacian of the Gaussian-smoothed surface; positive = concave-up", "1/m", source_layers=["ELEVATION"], parameters={"sigma_px": sg}),
            FeatureSpec("slope_break", "terrain", "magnitude of the spatial gradient of slope", "degree/m", window_px=3, source_layers=["SLOPE"]),
            FeatureSpec(f"lineament_density_w{lw}", "terrain", "fraction of Canny edge pixels from multi-azimuth hillshades in the window", "fraction", window_px=lw, source_layers=["ELEVATION"],
                        parameters={k: p[k] for k in ("lineament_azimuths", "lineament_altitude_deg", "canny_sigma", "canny_low", "canny_high", "min_valid_fraction")}),
        ]

    def extract(self, ctx: ExtractionContext) -> tuple[list[FeatureResult], list[dict[str, str]]]:
        p = _p(ctx.params)
        specs = {s.name: s for s in self.catalogue(p)}
        if "ELEVATION" not in ctx.arrays:
            return [], [_skip(n, "ELEVATION layer is not on the reference grid in the Phase 4 stack") for n in specs]
        z, tf, res, tile = ctx.arrays["ELEVATION"], ctx.transform, ctx.res_m, int(p["tile_px"])
        dx, dy = cell_sizes_m(ctx.grid["crs"], tf, z.shape[0])
        out: list[FeatureResult] = []
        notes_slope: list[str] = []

        def add(name: str, arr: np.ndarray, notes: list[str] | None = None, **extra: Any) -> None:
            s = specs[name]
            s.scale_m = None if s.window_px is None else s.window_px * res
            out.append(FeatureResult(s, arr, tf, True, notes or [], extra))

        rw, frac = p["relief_window_px"], p["min_valid_fraction"]
        add(f"local_relief_w{rw}", tiled_apply(z, lambda b, r0: terrain.local_relief(b, rw, frac), tile=tile, halo=rw // 2))
        add("terrain_ruggedness_index", tiled_apply(z, lambda b, r0: terrain.terrain_ruggedness(b), tile=tile, halo=1))
        sg = float(p["curvature_sigma_px"])
        halo_c = int(4 * sg + 0.5) + 1
        add(f"curvature_laplacian_s{_sigma_tag(sg)}",
            tiled_apply(z, lambda b, r0: terrain.curvature_laplacian(b, dx[r0:r0 + b.shape[0]], dy[r0:r0 + b.shape[0]], sg), tile=tile, halo=halo_c))
        if "SLOPE" in ctx.arrays:
            slope = ctx.arrays["SLOPE"]
        else:
            slope = slope_degrees(z, ctx.grid["crs"], tf)
            notes_slope.append("SLOPE layer absent from the stack; slope re-derived from the aligned ELEVATION (Horn)")
        add("slope_break", tiled_apply(slope, lambda b, r0: terrain.slope_break(b, dx[r0:r0 + b.shape[0]], dy[r0:r0 + b.shape[0]]), tile=tile, halo=1), notes_slope)
        gx, gy = terrain_gradients(z, ctx.grid["crs"], tf)  # lineaments need hysteresis tracing: whole array, not tiled
        lw = p["lineament_window_px"]
        dens, _ = terrain.lineament_density(gx, gy, lw, azimuths=tuple(p["lineament_azimuths"]), altitude_deg=p["lineament_altitude_deg"], sigma=p["canny_sigma"],
                                            low=p["canny_low"], high=p["canny_high"], min_valid_fraction=frac)
        add(f"lineament_density_w{lw}", dens, ["computed on the whole raster (Canny hysteresis is not tile-invariant)"])
        return out, []


class TextureExtractor:
    name = "texture"

    def catalogue(self, params: dict[str, Any]) -> list[FeatureSpec]:
        p = _p(params)
        w, lv = p["texture_window_px"], p["texture_levels"]
        return [FeatureSpec(f"glcm_{lay.lower()}_{prop.lower()}_w{w}", "texture", f"GLCM {prop} of {lay} per {w}x{w} block, mean of 4 directions, distance 1", "",
                            dimension="2d_block_grid", window_px=w, source_layers=[lay], parameters={"levels": lv, "stride_px": w})
                for lay in p["texture_layers"] for prop in texture.PROPS]

    def extract(self, ctx: ExtractionContext) -> tuple[list[FeatureResult], list[dict[str, str]]]:
        p = _p(ctx.params)
        out: list[FeatureResult] = []
        skipped: list[dict[str, str]] = []
        w, lv = int(p["texture_window_px"]), int(p["texture_levels"])
        tf = ctx.transform
        block_tf = Affine(tf.a * w, 0, tf.c, 0, tf.e * w, tf.f)
        by_name = {s.name: s for s in self.catalogue(p)}
        for lay in p["texture_layers"]:
            names = [f"glcm_{lay.lower()}_{prop.lower()}_w{w}" for prop in texture.PROPS]
            if lay not in ctx.arrays:
                skipped += [_skip(n, f"{lay} layer is not on the reference grid in the Phase 4 stack") for n in names]
                continue
            arr = ctx.arrays[lay]
            vmin, vmax = FIXED_BOUNDS.get(lay, (None, None))
            try:
                res = texture.glcm_blocks(arr, w, levels=lv, vmin=vmin, vmax=vmax)
            except FeatureError as exc:
                skipped += [_skip(n, str(exc)) for n in names]
                continue
            for prop, n in zip(texture.PROPS, names):
                s = by_name[n]
                s.scale_m = w * ctx.res_m
                out.append(FeatureResult(s, res.layers[prop], block_tf, False,
                                         [f"block grid: cell = {w} x reference cell ({w * ctx.res_m:g} m); partial edge blocks dropped; blocks with any missing pixel are NaN"],
                                         {"quantisation": {"vmin": res.vmin, "vmax": res.vmax, "levels": res.levels, "n_clipped": res.n_clipped,
                                                           "fixed_bounds": lay in FIXED_BOUNDS}, "blocks": res.n_blocks, "blocks_valid": res.n_blocks_valid}))
        return out, skipped


class ChangeExtractor:
    name = "change"
    _KINDS = (("NDVI", "ndvi_difference", "NDVI (dimensionless)"), ("INSAR_COHERENCE", "coherence_change", "coherence (dimensionless)"))

    def catalogue(self, params: dict[str, Any]) -> list[FeatureSpec]:
        return [FeatureSpec("ndvi_difference", "change", "NDVI later - earlier", "NDVI", source_layers=["NDVI"], temporal_kind="dynamic", requires_dated_real_inputs=True),
                FeatureSpec("coherence_change", "change", "InSAR coherence later - earlier", "", source_layers=["INSAR_COHERENCE"], temporal_kind="dynamic", requires_dated_real_inputs=True),
                FeatureSpec("insar_velocity_gradient", "change", "spatial gradient magnitude of one dated real InSAR velocity raster", "(velocity unit)/m", window_px=3,
                            source_layers=["INSAR_VELOCITY"], temporal_kind="dynamic", requires_dated_real_inputs=True)]

    def extract(self, ctx: ExtractionContext) -> tuple[list[FeatureResult], list[dict[str, str]]]:
        specs = {s.name: s for s in self.catalogue(ctx.params)}
        out: list[FeatureResult] = []
        skipped: list[dict[str, str]] = []
        tf = ctx.transform
        for lay, name, _ in self._KINDS:
            ins = ctx.change_inputs.get(lay, [])
            if len(ins) < 2:
                skipped.append(_skip(name, f"needs two dated REAL {lay} inputs on one grid; the Phase 4 stack holds {len(ins)}"))
                continue
            try:
                arr, info = change.ndvi_difference(ins[0], ins[1])
            except ChangeDetectionRefused as exc:
                skipped.append(_skip(name, f"refused: {exc}"))
                continue
            out.append(FeatureResult(specs[name], arr, tf, True, [], info))
        vel = ctx.change_inputs.get("INSAR_VELOCITY", [])
        if not vel:
            skipped.append(_skip("insar_velocity_gradient", "needs one dated REAL INSAR_VELOCITY input; none in the stack"))
        else:
            dx, dy = cell_sizes_m(ctx.grid["crs"], tf, vel[0].array.shape[0])
            try:
                arr, info = change.velocity_gradient(vel[0], dx, dy)
                out.append(FeatureResult(specs["insar_velocity_gradient"], arr, tf, True, [], info))
            except ChangeDetectionRefused as exc:
                skipped.append(_skip("insar_velocity_gradient", f"refused: {exc}"))
        return out, skipped


class FeatureRegistry:
    def __init__(self) -> None:
        self._items: dict[str, FeatureExtractor] = {}

    def register(self, ex: FeatureExtractor) -> None:
        if not isinstance(ex, FeatureExtractor):
            raise FeatureError("object does not implement the FeatureExtractor protocol")
        if ex.name in self._items:
            raise FeatureError(f"extractor {ex.name!r} already registered")
        bad = forbidden_names([s.name for s in ex.catalogue(DEFAULT_PARAMS)])
        if bad:
            raise FeatureError(f"feature names look like scores/predictions (forbidden by the ML policy): {bad}")
        self._items[ex.name] = ex

    def get(self, name: str) -> FeatureExtractor:
        try:
            return self._items[name]
        except KeyError:
            raise FeatureError(f"unknown extractor {name!r}") from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def all(self) -> list[FeatureExtractor]:
        return [self._items[n] for n in sorted(self._items)]

    def catalogue(self, params: dict[str, Any] | None = None) -> list[FeatureSpec]:
        return [s for ex in self.all() for s in ex.catalogue(params or {})]


REGISTRY = FeatureRegistry()
for _ex in (TerrainExtractor(), TextureExtractor(), ChangeExtractor()):
    REGISTRY.register(_ex)
