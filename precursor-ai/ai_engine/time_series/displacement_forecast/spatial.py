"""Spatial context for the per-pixel forecasters.

Why: per-pixel models cannot tell a local landslide signal from residual atmosphere, which moves whole
neighbourhoods together. Two options, both causal (a feature at date j uses only dates j-1 and j):

  E6a  neighbourhood features appended to the per-step inputs:
       nb3_inc   mean increment of the 3x3 ring around the pixel (centre excluded)
       nb9_inc   mean increment of the 9x9 ring (centre excluded)
       local_inc centre increment minus nb9_inc (spatial high-pass: removes long-wavelength atmosphere)
  E6b  PatchGRU: a small CNN encodes the 9x9 patch of (increment, validity, coherence) at every step,
       a GRU runs over the 6 steps, and static features + horizon join before the quantile head.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from scipy.ndimage import uniform_filter

from .models import QuantileHead


def increments(cum: np.ndarray, valid: np.ndarray):
    """inc_j = d_j - d_{j-1} with validity (both dates valid), as in dataset.build_samples."""
    inc = np.diff(cum, axis=0, prepend=np.nan).astype(np.float32)
    ok = np.isfinite(inc) & valid & np.roll(valid, 1, axis=0)
    ok[0] = False
    return np.where(ok, inc, 0.0).astype(np.float32), ok


def _ring_mean(x: np.ndarray, ok: np.ndarray, size: int) -> np.ndarray:
    """Mean of valid values in a size x size window excluding the centre, per date (axes 1, 2)."""
    w = ok.astype(np.float32)
    s = uniform_filter(x * w, size=(1, size, size), mode="constant") * size * size
    n = uniform_filter(w, size=(1, size, size), mode="constant") * size * size
    s, n = s - x * w, n - w
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(n >= 0.25 * (size * size - 1), s / np.maximum(n, 1e-6), np.nan)   # need >=25 % valid neighbours
    return out.astype(np.float32)


def neighbourhood_features(cum: np.ndarray, valid: np.ndarray) -> dict:
    inc, ok = increments(cum, valid)
    nb3, nb9 = _ring_mean(inc, ok, 3), _ring_mean(inc, ok, 9)
    local = np.where(ok, inc - np.nan_to_num(nb9), np.nan).astype(np.float32)
    return {"nb3_inc": nb3, "nb9_inc": nb9, "local_inc": local}


# ------------------------------------------------------------------ E6b: patch CNN + GRU
class PatchGRU(nn.Module):
    def __init__(self, c_patch: int, f_point: int, s_static: int, hidden: int = 64, emb: int = 32,
                 dropout: float = 0.1):
        super().__init__()
        self.cnn = nn.Sequential(nn.Conv2d(c_patch, 16, 3, padding=1), nn.GELU(),
                                 nn.Conv2d(16, emb, 3, padding=1), nn.GELU(),
                                 nn.AdaptiveAvgPool2d(1), nn.Flatten())
        self.gru = nn.GRU(emb + f_point, hidden, batch_first=True)
        self.head = QuantileHead(hidden + s_static, hidden, False, dropout)

    def forward(self, patch, point, s):  # patch [B,T,C,P,P], point [B,T,F], s [B,S]
        B, T = patch.shape[:2]
        z = self.cnn(patch.flatten(0, 1)).view(B, T, -1)
        out, _ = self.gru(torch.cat([z, point], -1))
        return self.head(torch.cat([out[:, -1], s], 1))


class PatchSource:
    """Holds per-date grids on the device and gathers [B, W, C, P, P] patches for (issue index, row, col)."""

    def __init__(self, grids: np.ndarray, window: int, patch: int, device: str):
        # grids [T, C, H, W] already normalised; zero-padded so every patch is inside
        self.r = patch // 2
        g = np.pad(grids, ((0, 0), (0, 0), (self.r, self.r), (self.r, self.r)))
        self.g = torch.from_numpy(g.astype(np.float32)).to(device)
        self.window, self.patch, self.device = window, patch, device
        off = torch.arange(patch, device=device)
        self.dy, self.dx = off.view(1, 1, patch, 1), off.view(1, 1, 1, patch)
        self.dt = torch.arange(-window + 1, 1, device=device).view(1, window)

    def gather(self, k: torch.Tensor, r: torch.Tensor, c: torch.Tensor) -> torch.Tensor:
        """Advanced indexing straight into the patch elements (never materialises full grids per sample)."""
        B, W, C, P = len(k), self.window, self.g.shape[1], self.patch
        ti = (k.view(B, 1) + self.dt).view(B, W, 1, 1, 1)                # date index
        ci = torch.arange(C, device=self.device).view(1, 1, C, 1, 1)
        ri = r.view(B, 1, 1, 1, 1) + self.dy.view(1, 1, 1, P, 1)          # padded coords: centre at r + P//2
        cj = c.view(B, 1, 1, 1, 1) + self.dx.view(1, 1, 1, 1, P)
        return self.g[ti, ci, ri, cj]                                    # [B, W, C, P, P]


def masked_bilateral(cum: np.ndarray, valid: np.ndarray, sigma_s: float = 1.5, sigma_r: float = 3.0,
                     radius: int = 2) -> np.ndarray:
    """Edge-preserving, mask-aware bilateral filter per date (skill Step 5). Inputs only, never labels.

    Weights = spatial Gaussian x range Gaussian on the value difference to the centre. Invalid pixels get
    zero weight, so values never leak across masked holes. Invalid centres stay NaN (no filling), and
    the range term keeps sharp landslide boundaries from being averaged away.
    """
    T, H, W = cum.shape
    x = np.where(valid, cum, 0.0).astype(np.float64)
    v = valid.astype(np.float64)
    xp = np.pad(x, ((0, 0), (radius, radius), (radius, radius)))
    vp = np.pad(v, ((0, 0), (radius, radius), (radius, radius)))
    num = np.zeros((T, H, W)); den = np.zeros((T, H, W))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ws = np.exp(-(dy * dy + dx * dx) / (2 * sigma_s ** 2))
            nb = xp[:, radius + dy:radius + dy + H, radius + dx:radius + dx + W]
            nv = vp[:, radius + dy:radius + dy + H, radius + dx:radius + dx + W]
            w = ws * nv * np.exp(-((nb - x) ** 2) / (2 * sigma_r ** 2))
            num += w * nb; den += w
    out = np.where(valid & (den > 0), num / np.maximum(den, 1e-12), np.nan)
    return out.astype(np.float32)
