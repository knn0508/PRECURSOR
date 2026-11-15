"""Causal noise-aware state-space estimator of single-LOS motion (skill v3, Phase 5).

Extends the v2 local-linear-trend filter (kalman_trend.py, kept unchanged) with pre-specified, physically
motivated options. Filtering only: the state at date t uses observations at dates <= t.

State x = [s, v]: latent LOS level (mm) and LOS velocity (mm/day). Between acquisitions dt days apart
  s' = s + v dt, v' = v + w,  Q = q [[dt^3/3, dt^2/2], [dt^2/2, dt]]          (irregular dt, true elapsed days)
Observation  z_t = s_t + e_t,  e_t ~ N(0, R_t)  only where z_t is a VALID observation; otherwise no update and
the uncertainty keeps growing (masked-but-finite values must be passed as NaN by the caller).

Options (each a falsifiable hypothesis, chosen on 2023 validation, never on test):
  qa_alpha     R_t = R0 * (1 + qa_alpha * (1 - coherence_t))    low temporal coherence -> noisier observation
  huber_c      robust update: if |innovation| / sqrt(S) > c, R_t is inflated so the standardized innovation = c
  boundary_var extra level variance at the first date of a new OPERA ministack (re-referencing adds a shared
               step: every later value of that ministack carries the reference-date error)
  cp_nis       change-point flag: if the normalized innovation squared exceeds cp_nis BEFORE update, velocity
               variance is inflated by cp_vel_var (uncertainty expands when constant velocity is violated)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass(frozen=True)
class SSConfig:
    R0: float = 8.0
    q: float = 1e-5
    qa_alpha: float = 0.0
    huber_c: float | None = None
    boundary_var: float = 0.0
    cp_nis: float | None = None
    cp_vel_var: float = 0.0
    v0_var: float = 1.0

    def name(self):
        return ",".join(f"{k}={v}" for k, v in asdict(self).items())


def run_filter(y: np.ndarray, td: np.ndarray, cfg: SSConfig, coherence: np.ndarray | None = None,
               boundary: np.ndarray | None = None) -> dict:
    """y: (T, P) valid-only observations (NaN elsewhere); td: (T,) days; coherence: (T, P); boundary: (T,) bool."""
    y = np.asarray(y, float); td = np.asarray(td, float)
    T, P = y.shape
    if np.any(np.diff(td) <= 0):
        raise ValueError("acquisition days must be strictly increasing")
    s = np.zeros(P); v = np.zeros(P)
    Pss = np.full(P, 1e4); Psv = np.zeros(P); Pvv = np.full(P, cfg.v0_var)
    started = np.zeros(P, bool)
    keys = ("level", "vel", "var_level", "var_vel", "cov_lv", "R_used", "nis")
    out = {k: np.full((T, P), np.nan, np.float32) for k in keys}
    out["cp_flag"] = np.zeros((T, P), bool)
    ll = np.zeros(P); n_upd = np.zeros(P, np.int32)
    for t in range(T):
        dt = td[t] - td[t - 1] if t else 0.0
        if dt > 0:
            s = s + v * dt
            Pss, Psv, Pvv = (Pss + 2 * dt * Psv + dt * dt * Pvv + cfg.q * dt ** 3 / 3,
                             Psv + dt * Pvv + cfg.q * dt ** 2 / 2, Pvv + cfg.q * dt)
        if boundary is not None and boundary[t] and cfg.boundary_var > 0:
            Pss = Pss + cfg.boundary_var
        z = y[t]
        obs = np.isfinite(z)
        R = np.full(P, cfg.R0)
        if coherence is not None and cfg.qa_alpha:
            c = np.clip(np.nan_to_num(coherence[t], nan=0.0), 0, 1)
            R = cfg.R0 * (1 + cfg.qa_alpha * (1 - c))
        init = obs & ~started
        s = np.where(init, z, s); Pss = np.where(init, R, Pss); Psv = np.where(init, 0.0, Psv); Pvv = np.where(init, cfg.v0_var, Pvv)
        started |= init
        upd = obs & ~init
        innov = np.where(upd, z - s, 0.0)
        S = Pss + R
        nis = innov ** 2 / S
        if cfg.cp_nis is not None and cfg.cp_vel_var > 0:
            cp = upd & (nis > cfg.cp_nis)
            Pvv = np.where(cp, Pvv + cfg.cp_vel_var, Pvv)
            out["cp_flag"][t] = cp
        if cfg.huber_c is not None:
            r = np.sqrt(nis)
            k = np.where(upd & (r > cfg.huber_c), r / cfg.huber_c, 1.0)      # inflate S so standardized innovation = c
            R = np.where(k > 1, (Pss + R) * k - Pss, R)
        S = Pss + R
        Ks, Kv = Pss / S, Psv / S
        ll += np.where(upd, -0.5 * (np.log(2 * np.pi * S) + innov ** 2 / S), 0.0)
        n_upd += upd
        s = np.where(upd, s + Ks * innov, s); v = np.where(upd, v + Kv * innov, v)
        Pss, Psv, Pvv = (np.where(upd, (1 - Ks) * Pss, Pss), np.where(upd, (1 - Ks) * Psv, Psv),
                         np.where(upd, Pvv - Kv * Psv, Pvv))
        live = started
        for k_, val in (("level", s), ("vel", v), ("var_level", Pss), ("var_vel", Pvv), ("cov_lv", Psv)):
            out[k_][t] = np.where(live, val, np.nan)
        out["R_used"][t] = np.where(obs, R, np.nan)
        out["nis"][t] = np.where(upd, nis, np.nan)
    out["loglik"] = ll; out["n_updates"] = n_upd
    return out


def forecast_increment(o: dict, k: np.ndarray, p: np.ndarray, h: np.ndarray, z_t: np.ndarray, cfg: SSConfig,
                       lam: float = 1.0, R_next: float | np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Forecast of the next observed increment z_{t+h} - z_t and, for lam = 1, its predictive SD.

    mean = v h - lam (z_t - s_t|t). For lam = 1 this is the model-consistent E[z_{t+h} - z_t | z_<=t] with
    Var = Var(s_{t+h} | z_<=t) + R_{t+h}  (z_t is known at issue time).
    """
    s, v = o["level"][k, p].astype(float), o["vel"][k, p].astype(float)
    Pss, Psv, Pvv = (o[n][k, p].astype(float) for n in ("var_level", "cov_lv", "var_vel"))
    mean = v * h - lam * (z_t - s)
    Rn = cfg.R0 if R_next is None else R_next
    var = Pss + 2 * h * Psv + h * h * Pvv + cfg.q * h ** 3 / 3 + Rn
    return mean, np.sqrt(var)


def velocity_interval(o: dict, k, p, z=1.2816) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Causal LOS velocity estimate (mm/day) with a central 80 % interval (labelled model-inferred)."""
    v = o["vel"][k, p].astype(float); sd = np.sqrt(o["var_vel"][k, p].astype(float))
    return v, v - z * sd, v + z * sd


def ministack_boundaries(times, granule_names) -> np.ndarray:
    """True at the first stack date whose source granule uses a new reference date (re-referencing step)."""
    import re
    import pandas as pd
    ref_of = {}
    for g in granule_names:
        m = re.search(r"_(\d{8})T\d{6}Z_(\d{8})T\d{6}Z_v", g)
        ref_of[pd.Timestamp(m.group(2))] = pd.Timestamp(m.group(1))
    refs = [ref_of.get(pd.Timestamp(t).normalize()) for t in times]
    b = np.zeros(len(times), bool)
    for i in range(1, len(times)):
        b[i] = refs[i] is not None and refs[i - 1] is not None and refs[i] != refs[i - 1]
    return b
