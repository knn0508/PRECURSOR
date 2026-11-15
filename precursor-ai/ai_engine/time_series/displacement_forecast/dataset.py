"""Causal per-pixel sequence samples from a cumulative LOS stack.

Sample (pixel p, issue index k):
  inputs  use only dates t_{k-W} .. t_k   (W increments)
  target  y = d(t_m) - d(t_k), t_m = first acquisition with
          |t_m - t_k - horizon| <= tol      (LOS mm over h = t_m - t_k days)

Rainfall features are aggregated strictly over (t_{j-1}, t_j] and the 30 days
before t_j, so nothing after the issue date t_k enters the inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DYN_BASE = ["inc_mm", "dt_days", "vel_mm_day", "coherence", "valid"]
DYN_RAIN = ["rain_interval_mm", "rain_30d_mm"]


@dataclass
class SampleSet:
    X: np.ndarray            # [N, W, F] float32
    S: np.ndarray            # [N, S] float32 static (+ horizon)
    y: np.ndarray            # [N] target LOS increment, mm
    h_days: np.ndarray       # [N] actual horizon in days
    issue_time: np.ndarray   # [N] datetime64
    target_time: np.ndarray  # [N] datetime64
    pix: np.ndarray          # [N, 2] (row, col)
    last_vel: np.ndarray     # [N] |vel| of last input interval, mm/day (for crossing labels)
    feat_names: list = field(default_factory=list)
    static_names: list = field(default_factory=list)

    def subset(self, idx):
        return SampleSet(self.X[idx], self.S[idx], self.y[idx], self.h_days[idx],
                         self.issue_time[idx], self.target_time[idx], self.pix[idx],
                         self.last_vel[idx], self.feat_names, self.static_names)

    def __len__(self):
        return len(self.y)


def target_index(times: pd.DatetimeIndex, horizon: float, tol: float) -> np.ndarray:
    """For each issue index k, the index m of the first date within horizon±tol (or -1)."""
    t = times.values.astype("datetime64[s]").astype(np.int64) / 86400.0
    out = np.full(len(t), -1, int)
    for k in range(len(t)):
        d = t - t[k]
        ok = np.where((d >= horizon - tol) & (d <= horizon + tol))[0]
        if len(ok):
            out[k] = ok[np.argmin(np.abs(d[ok] - horizon))]
    return out


def rain_features(times: pd.DatetimeIndex, rain: pd.Series | None) -> np.ndarray | None:
    """[T, 2]: rain in (t_{j-1}, t_j] and in the 30 days ending at t_j (mm). Past only."""
    if rain is None:
        return None
    r = rain.sort_index()
    cs = r.cumsum()
    # use days strictly before the acquisition day: a daily total for day t_j is mostly
    # rain that falls after a ~02 UTC Sentinel-1 pass, i.e. after issue time
    day = times.normalize() - pd.Timedelta(days=1)

    def cum_at(ts):
        v = cs.reindex(cs.index.union([ts])).ffill().loc[ts]
        return float(v) if np.isfinite(v) else np.nan

    c_now = np.array([cum_at(d) for d in day])
    c_prev = np.concatenate([[np.nan], c_now[:-1]])
    c_30 = np.array([cum_at(d - pd.Timedelta(days=30)) for d in day])
    return np.stack([c_now - c_prev, c_now - c_30], 1).astype(np.float32)


def build_samples(cum: np.ndarray, valid: np.ndarray, coh: np.ndarray, times: pd.DatetimeIndex,
                  static: np.ndarray, static_names: list, rain: pd.Series | None = None,
                  window: int = 6, horizon: float = 12.0, tol: float = 3.0,
                  min_valid_steps: int = 4, pixel_stride: int = 2,
                  pixel_mask: np.ndarray | None = None, issue_indices=None,
                  extra_dyn: dict | None = None) -> SampleSet:
    """cum/valid/coh: [T, H, W]; static: [S, H, W].

    issue_indices: if given, build *inference* samples only for these issue indices,
    with no target required (y = NaN, horizon = nominal `horizon`).
    extra_dyn: optional {name: [T, H, W]} per-date grids (e.g. spatial-context features). Each must use
    only data of its own date (causal); NaN becomes 0 and they are appended to the dynamic features.
    """
    infer = issue_indices is not None
    from .physics_checks import assert_time_order
    times = assert_time_order(times)                 # shuffled / duplicated dates fail loudly
    T, H, Wd = cum.shape
    if len(times) != T:
        raise ValueError(f"{len(times)} times for a stack of {T} dates")
    tdays = times.values.astype("datetime64[s]").astype(np.int64) / 86400.0
    dt = np.diff(tdays, prepend=np.nan).astype(np.float32)               # [T]
    inc = np.diff(cum, axis=0, prepend=np.nan).astype(np.float32)        # [T,H,W] inc_j = d_j - d_{j-1}
    inc_ok = np.isfinite(inc) & valid & np.roll(valid, 1, axis=0)
    inc_ok[0] = False
    vel = inc / dt[:, None, None]
    rf = rain_features(times, rain)
    tgt = target_index(times, horizon, tol)

    rows, cols = np.mgrid[0:H:pixel_stride, 0:Wd:pixel_stride]
    rows, cols = rows.ravel(), cols.ravel()
    if pixel_mask is not None:
        keep = pixel_mask[rows, cols]
        rows, cols = rows[keep], cols[keep]

    extra_dyn = extra_dyn or {}
    feat_names = DYN_BASE + (DYN_RAIN if rf is not None else []) + list(extra_dyn)
    Xs, Ss, ys, hs, it, tt, px, lv = [], [], [], [], [], [], [], []
    for k in (issue_indices if infer else range(window, T)):
        m = -1 if infer else tgt[k]
        if m < 0 and not infer:
            continue
        sl = slice(k - window + 1, k + 1)
        ok_steps = inc_ok[sl][:, rows, cols]                              # [W, P]
        if infer:
            y = np.full(len(rows), np.nan, np.float32)
            good = (ok_steps.sum(0) >= min_valid_steps) & valid[k, rows, cols]
        else:
            y = cum[m, rows, cols] - cum[k, rows, cols]
            good = (ok_steps.sum(0) >= min_valid_steps) & np.isfinite(y) & valid[m, rows, cols] & valid[k, rows, cols]
        good &= ok_steps[-1]  # last interval must be observed (needed for crossing label)
        if not good.any():
            continue
        r_, c_ = rows[good], cols[good]
        okw = ok_steps[:, good]
        f_inc = np.where(okw, inc[sl][:, r_, c_], 0.0)
        f_vel = np.where(okw, vel[sl][:, r_, c_], 0.0)
        f_coh = np.nan_to_num(coh[sl][:, r_, c_], nan=0.0)
        f_dt = np.broadcast_to(dt[sl][:, None], f_inc.shape)
        feats = [f_inc, f_dt, f_vel, f_coh, okw.astype(np.float32)]
        if rf is not None:
            feats += [np.broadcast_to(np.nan_to_num(rf[sl, i])[:, None], f_inc.shape) for i in range(2)]
        for g in extra_dyn.values():
            feats.append(np.nan_to_num(g[sl][:, r_, c_]).astype(np.float32))
        X = np.stack(feats, -1).transpose(1, 0, 2)                        # [P, W, F]
        h = np.float32(horizon if infer else tdays[m] - tdays[k])
        S = np.concatenate([static[:, r_, c_].T, np.full((len(r_), 1), h, np.float32)], 1)
        Xs.append(X.astype(np.float32)); Ss.append(S.astype(np.float32))
        ys.append(y[good].astype(np.float32)); hs.append(np.full(len(r_), h, np.float32))
        it.append(np.full(len(r_), times.values[k])); tt.append(np.full(len(r_), times.values[k] + np.timedelta64(int(h * 86400), 's') if infer else times.values[m]))
        px.append(np.stack([r_, c_], 1)); lv.append(np.abs(f_vel[-1]).astype(np.float32))
    if not Xs:
        raise ValueError("no valid samples; check masks / horizon tolerance")
    return SampleSet(np.concatenate(Xs), np.concatenate(Ss), np.concatenate(ys), np.concatenate(hs),
                     np.concatenate(it), np.concatenate(tt), np.concatenate(px), np.concatenate(lv),
                     feat_names, list(static_names) + ["horizon_days"])


def chronological_split(ss: SampleSet, train_end: str, val_end: str) -> dict:
    """Train: target < train_end. Val: issue >= train_end and target < val_end. Test: issue >= val_end.

    Using the *target* date for the upper bound means no training label lies in
    the validation/test period (embargo against horizon overlap).
    """
    te, ve = np.datetime64(train_end), np.datetime64(val_end)
    tr = ss.target_time < te
    va = (ss.issue_time >= te) & (ss.target_time < ve)
    ts = ss.issue_time >= ve
    return {"train": np.where(tr)[0], "val": np.where(va)[0], "test": np.where(ts)[0]}


class Scaler:
    """Mean/std scaler fitted on training rows only."""

    def fit(self, ss: SampleSet):
        """Dynamic-feature stats use observed steps only: unobserved steps are zero-filled
        placeholders (flagged by `valid`) and would otherwise bias mean/std toward 0."""
        X = ss.X.reshape(-1, ss.X.shape[-1])
        self.xm, self.xs = X.mean(0), X.std(0) + 1e-6
        if "valid" in ss.feat_names:
            vi = ss.feat_names.index("valid")
            obs = X[:, vi] > 0
            if obs.any():
                for j in range(X.shape[1]):
                    if j != vi:
                        self.xm[j], self.xs[j] = X[obs, j].mean(), X[obs, j].std() + 1e-6
        self.sm, self.sd = ss.S.mean(0), ss.S.std(0) + 1e-6
        self.ym, self.ys = float(ss.y.mean()), float(ss.y.std() + 1e-6)
        return self

    def tx(self, ss: SampleSet):
        return ((ss.X - self.xm) / self.xs).astype(np.float32), ((ss.S - self.sm) / self.sd).astype(np.float32)

    def ty(self, y):
        return ((y - self.ym) / self.ys).astype(np.float32)

    def iy(self, z):
        return z * self.ys + self.ym


def crossing_threshold(train: SampleSet, q: float = 0.95, noise_mult: float = 3.0) -> dict:
    """Train-only movement-speed threshold tau (mm/day) for onset proxy labels.

    tau = max(q-quantile of |interval velocity|, noise_mult * robust noise),
    robust noise = 1.4826 * MAD of |velocity| (a crude, documented noise floor).
    """
    v = np.abs(train.y / train.h_days)
    qv = float(np.quantile(v, q))
    mad = float(1.4826 * np.median(np.abs(v - np.median(v))))
    return {"tau_mm_day": max(qv, noise_mult * mad), "quantile": q, "q_value": qv,
            "noise_mad_mm_day": mad, "noise_mult": noise_mult}


def crossing_labels(ss: SampleSet, tau: float) -> np.ndarray:
    """1 if last observed interval speed <= tau and target-horizon speed > tau (Strnad-style onset)."""
    return ((ss.last_vel <= tau) & (np.abs(ss.y / ss.h_days) > tau)).astype(np.float32)
