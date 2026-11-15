"""Sequence forecasters (PyTorch).

Paper lineage (adapted, not reproduced):
  MLP / LSTM / GRU ........ Nava et al. 2023, Landslides 20:2111-2129, doi:10.1007/s10346-023-02104-9
  TCN, LSTM->TCN .......... Li et al. 2025, Nat Hazards 121:3857-3884, doi:10.1007/s11069-024-06937-y
  multi-task onset head ... Strnad et al. 2026, Sci Rep 16:196, doi:10.1038/s41598-025-29084-1

All models map x [B, T, F] and static s [B, S] to
  q   [B, 3]  ordered quantiles (q10, q50, q90) of the scaled target
  cls [B]     onset logit (only meaningful when trained with the crossing head)
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class QuantileHead(nn.Module):
    """Median + non-negative spacings => q10 <= q50 <= q90 by construction."""

    def __init__(self, d_in: int, hidden: int = 64, multitask: bool = False, dropout: float = 0.0):
        super().__init__()
        self.body = nn.Sequential(nn.Dropout(dropout), nn.Linear(d_in, hidden), nn.GELU(), nn.Dropout(dropout))
        self.q = nn.Linear(hidden, 3)
        self.cls = nn.Linear(hidden, 1) if multitask else None

    def forward(self, z):
        h = self.body(z)
        o = self.q(h)
        med = o[:, 0]
        lo = med - F.softplus(o[:, 1])
        hi = med + F.softplus(o[:, 2])
        cls = self.cls(h).squeeze(-1) if self.cls is not None else torch.zeros_like(med)
        return torch.stack([lo, med, hi], 1), cls


class MLP(nn.Module):
    def __init__(self, T, F_, S, hidden=64, dropout=0.1, multitask=False):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(T * F_ + S, hidden), nn.GELU(), nn.Dropout(dropout),
                                 nn.Linear(hidden, hidden), nn.GELU())
        self.head = QuantileHead(hidden, hidden, multitask, dropout)

    def forward(self, x, s):
        return self.head(self.net(torch.cat([x.flatten(1), s], 1)))


class RNN(nn.Module):
    def __init__(self, T, F_, S, hidden=64, layers=1, cell="lstm", dropout=0.1, multitask=False):
        super().__init__()
        R = nn.LSTM if cell == "lstm" else nn.GRU
        self.rnn = R(F_, hidden, num_layers=layers, batch_first=True,
                     dropout=dropout if layers > 1 else 0.0)
        self.head = QuantileHead(hidden + S, hidden, multitask, dropout)

    def forward(self, x, s):
        out, _ = self.rnn(x)
        return self.head(torch.cat([out[:, -1], s], 1))


class CausalConv1d(nn.Conv1d):
    """Conv1d with left-only padding: output[t] depends on input[<= t]."""

    def __init__(self, c_in, c_out, k, dilation):
        super().__init__(c_in, c_out, k, dilation=dilation)
        self.left = (k - 1) * dilation

    def forward(self, x):  # x [B, C, T]
        return super().forward(F.pad(x, (self.left, 0)))


class TCNBlock(nn.Module):
    def __init__(self, c_in, c_out, k, dilation, dropout):
        super().__init__()
        self.c1 = CausalConv1d(c_in, c_out, k, dilation)
        self.c2 = CausalConv1d(c_out, c_out, k, dilation)
        self.drop = nn.Dropout(dropout)
        self.res = nn.Conv1d(c_in, c_out, 1) if c_in != c_out else nn.Identity()

    def forward(self, x):
        h = self.drop(F.gelu(self.c1(x)))
        h = self.drop(F.gelu(self.c2(h)))
        return F.gelu(h + self.res(x))


class TCN(nn.Module):
    def __init__(self, c_in, channels=64, k=3, dilations=(1, 2, 4, 8), dropout=0.1):
        super().__init__()
        blocks, c = [], c_in
        for d in dilations:
            blocks.append(TCNBlock(c, channels, k, d, dropout))
            c = channels
        self.net = nn.Sequential(*blocks)

    def forward(self, x):  # [B, T, C] -> [B, T, channels]
        return self.net(x.transpose(1, 2)).transpose(1, 2)


def receptive_field(k: int, dilations) -> int:
    """Steps seen by the last output of a TCN with two causal convs per block."""
    return 1 + 2 * (k - 1) * sum(dilations)


def dilations_for(T: int, k: int = 3) -> tuple:
    """Smallest doubling dilation stack whose receptive field covers the T-step window.

    With T=6, k=3 this gives (1, 2) -> RF 13. Larger stacks (e.g. 1,2,4,8 -> RF 61)
    would make the extra blocks see mostly zero padding.
    """
    d = [1]
    while receptive_field(k, d) < T:
        d.append(d[-1] * 2)
    return tuple(d)


class TCNOnly(nn.Module):
    def __init__(self, T, F_, S, hidden=64, dropout=0.1, multitask=False, dilations=None):
        super().__init__()
        dilations = dilations or dilations_for(T)
        self.tcn = TCN(F_, hidden, 3, dilations, dropout)
        self.head = QuantileHead(hidden + S, hidden, multitask, dropout)

    def forward(self, x, s):
        return self.head(torch.cat([self.tcn(x)[:, -1], s], 1))


class LSTMTCN(nn.Module):
    """LSTM encoder (long-term state) followed by causal dilated TCN blocks (local change)."""

    def __init__(self, T, F_, S, hidden=64, dropout=0.1, multitask=False, dilations=None):
        super().__init__()
        dilations = dilations or dilations_for(T)
        self.lstm = nn.LSTM(F_, hidden, batch_first=True)
        self.tcn = TCN(hidden, hidden, 3, dilations, dropout)
        self.head = QuantileHead(hidden + S, hidden, multitask, dropout)

    def forward(self, x, s):
        h, _ = self.lstm(x)
        return self.head(torch.cat([self.tcn(h)[:, -1], s], 1))


def build(name: str, T: int, F_: int, S: int, multitask: bool = False, hidden: int = 64, dropout: float = 0.1):
    name = name.lower()
    if name == "mlp":
        return MLP(T, F_, S, hidden, dropout=dropout, multitask=multitask)
    if name in ("lstm", "gru"):
        return RNN(T, F_, S, hidden, cell=name, dropout=dropout, multitask=multitask)
    if name == "tcn":
        return TCNOnly(T, F_, S, hidden, dropout=dropout, multitask=multitask)
    if name in ("lstm_tcn", "lstm-tcn"):
        return LSTMTCN(T, F_, S, hidden, dropout=dropout, multitask=multitask)
    raise ValueError(name)


def n_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)
