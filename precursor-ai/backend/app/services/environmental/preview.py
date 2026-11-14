"""Quick-look PNGs and legends for environmental raster layers.

Rendering never alters data: nodata/NaN is fully transparent (never drawn as zero), the colour scale is returned to
the caller (legend), and aspect is drawn on a circular hue wheel so 359 and 1 degrees look alike.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling

from app.services.environmental.types import LayerKind

# 5-stop sequential ramp (dark blue -> teal -> green -> yellow -> light); colour-blind friendly enough for a quick look.
_RAMP = np.array([[8, 29, 88], [34, 94, 168], [29, 145, 192], [127, 205, 187], [255, 255, 217]], dtype=float)
RAMP_HEX = ["#081d58", "#225ea8", "#1d91c0", "#7fcdbb", "#ffffd9"]  # keep identical to _RAMP (legend uses it)
DIVERGING_HEX = ["#1f1fcc", "#ffffff", "#cc1f1f"]  # negative, zero, positive (as drawn)
_DIVERGING = {LayerKind.INSAR_DISPLACEMENT, LayerKind.INSAR_VELOCITY}
_PALETTE = ["#6e7681", "#1f6feb", "#2da44e", "#d29922", "#cf222e", "#8250df", "#0e8a8a", "#bf3989", "#7d4e24", "#57606a",
            "#a371f7"]


def scale_kind(kind: str) -> str:
    if kind in (LayerKind.LAND_COVER, LayerKind.LITHOLOGY):
        return "categorical"
    if kind == LayerKind.ASPECT:
        return "circular"
    return "continuous"


def _read(path: Path, max_size: int) -> np.ndarray:
    with rasterio.open(path) as ds:
        s = max(ds.width, ds.height) / max_size
        h, w = max(1, int(ds.height / max(s, 1))), max(1, int(ds.width / max(s, 1)))
        # nearest keeps categorical ids intact and never invents values
        return ds.read(1, out_shape=(h, w), resampling=Resampling.nearest, masked=False).astype("float64")


def value_range(path: Path, kind: str) -> tuple[float | None, float | None]:
    a = _read(path, 512)
    ok = np.isfinite(a)
    if not ok.any():
        return None, None
    if kind == LayerKind.ASPECT:
        return 0.0, 360.0
    if kind in _DIVERGING:
        m = float(np.percentile(np.abs(a[ok]), 98)) or 1.0
        return -m, m
    return float(np.percentile(a[ok], 2)), float(np.percentile(a[ok], 98))


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def render_png(path: Path, kind: str, *, vmin: float | None = None, vmax: float | None = None,
               classes: list[dict[str, Any]] | None = None, max_size: int = 512) -> bytes:
    a = _read(path, max_size)
    ok = np.isfinite(a)
    h, w = a.shape
    rgba = np.zeros((4, h, w), dtype="uint8")
    k = scale_kind(kind)
    if k == "categorical":
        colors = {int(c["id"]): _hex_rgb(c["color"]) for c in (classes or [])}
        for cid in np.unique(a[ok]).astype(int):
            rgb = colors.get(int(cid), (128, 128, 128))  # unknown ids stay visible in grey and are reported by the processor
            m = ok & (a == cid)
            for i in range(3):
                rgba[i][m] = rgb[i]
    elif k == "circular":
        hue = np.where(ok, a % 360.0, 0.0) / 360.0
        # HSV(hue, 0.85, 0.95) -> RGB without matplotlib
        i = np.floor(hue * 6).astype(int) % 6
        f = hue * 6 - np.floor(hue * 6)
        v, s = 0.95, 0.85
        p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
        r = np.choose(i, [v + 0 * f, q, p, p, t, v + 0 * f])
        g = np.choose(i, [t, v + 0 * f, v + 0 * f, q, p, p])
        b = np.choose(i, [p, p, t, v + 0 * f, v + 0 * f, q])
        for ch, arr in enumerate((r, g, b)):
            rgba[ch] = (255 * arr).astype("uint8")
    elif kind in _DIVERGING:
        m = vmax or 1.0
        t = np.clip(np.where(ok, a, 0) / m, -1, 1)
        pos, neg = np.clip(t, 0, 1), np.clip(-t, 0, 1)
        rgba[0] = (255 * (1 - neg * 0.8)).astype("uint8")
        rgba[1] = (255 * (1 - pos * 0.8 - neg * 0.8)).clip(0, 255).astype("uint8")
        rgba[2] = (255 * (1 - pos * 0.8)).astype("uint8")
    else:
        lo = vmin if vmin is not None else (float(np.nanmin(a[ok])) if ok.any() else 0.0)
        hi = vmax if vmax is not None else (float(np.nanmax(a[ok])) if ok.any() else 1.0)
        t = np.clip((np.where(ok, a, lo) - lo) / ((hi - lo) or 1.0), 0, 1) * (len(_RAMP) - 1)
        i0 = np.floor(t).astype(int).clip(0, len(_RAMP) - 2)
        f = (t - i0)[..., None]
        rgb = _RAMP[i0] * (1 - f) + _RAMP[i0 + 1] * f
        for ch in range(3):
            rgba[ch] = rgb[..., ch].astype("uint8")
    rgba[3] = np.where(ok, 255, 0).astype("uint8")  # nodata transparent, never zero-coloured
    with rasterio.MemoryFile() as mem:
        with mem.open(driver="PNG", width=w, height=h, count=4, dtype="uint8") as dst:
            dst.write(rgba)
        return mem.read()


def default_class_colors(ids: list[int]) -> list[dict[str, Any]]:
    """Fallback swatches when a provider did not supply official colours (names stay 'class N': never invented)."""
    return [{"id": int(i), "name": f"class {int(i)}", "color": _PALETTE[n % len(_PALETTE)]} for n, i in enumerate(sorted(ids))]
