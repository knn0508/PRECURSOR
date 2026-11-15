"""One-sided local-linear-trend Kalman filter over irregular acquisitions (skill v2, T3).

State x = [s, v] (latent cumulative LOS level in mm, velocity in mm/day). Observation z_t = s_t + e_t with
e_t ~ N(0, R) (measurement error of the cumulative level). Between acquisitions dt days apart:
  s' = s + v dt, v' = v + w with continuous white-noise acceleration of spectral density q:
  Q = q * [[dt^3/3, dt^2/2], [dt^2/2, dt]]
Filtering only (no RTS smoother), so the state at t uses observations <= t. Missing dates skip the update.
Outputs per date: filtered level s_t|t, velocity v_t|t, their variances, and the innovation log-likelihood.

Forecasts for a horizon h:
  trend objective          v_t|t * h
  next observed increment  E[z_{t+h} - z_t | z_<=t] = s_t|t + v_t|t h - z_t = v_t|t h - (z_t - s_t|t)
The second form is the model-consistent version of "trend - lambda * deviation" with lambda = 1.
"""
from __future__ import annotations

import numpy as np


def filter_series(y: np.ndarray, td: np.ndarray, R: float, q: float, v0_var: float = 1.0, s0_var: float = 1e4):
    T, P = y.shape
    s = np.zeros(P); v = np.zeros(P)
    Pss = np.full(P, s0_var); Psv = np.zeros(P); Pvv = np.full(P, v0_var)
    started = np.zeros(P, bool)
    out = {k: np.full((T, P), np.nan, np.float32) for k in ("level", "vel", "var_level", "var_vel")}
    ll = np.zeros(P); n_upd = np.zeros(P, np.int32)
    prev_t = td[0]
    for t in range(T):
        dt = td[t] - prev_t if t else 0.0
        prev_t = td[t]
        if dt > 0:
            s = s + v * dt
            Pss, Psv, Pvv = (Pss + 2 * dt * Psv + dt * dt * Pvv + q * dt ** 3 / 3,
                             Psv + dt * Pvv + q * dt ** 2 / 2,
                             Pvv + q * dt)
        z = y[t]
        obs = np.isfinite(z)
        init = obs & ~started                                 # first valid observation sets the level
        s = np.where(init, z, s); Pss = np.where(init, R, Pss); Psv = np.where(init, 0.0, Psv); Pvv = np.where(init, v0_var, Pvv)
        started |= init
        upd = obs & ~init
        S = Pss + R
        innov = np.where(upd, z - s, 0.0)
        Ks, Kv = Pss / S, Psv / S
        s = np.where(upd, s + Ks * innov, s); v = np.where(upd, v + Kv * innov, v)
        Pss, Psv, Pvv = (np.where(upd, (1 - Ks) * Pss, Pss), np.where(upd, (1 - Ks) * Psv, Psv),
                         np.where(upd, Pvv - Kv * Psv, Pvv))
        ll += np.where(upd, -0.5 * (np.log(2 * np.pi * S) + innov ** 2 / S), 0.0)
        n_upd += upd
        live = started
        out["level"][t] = np.where(live, s, np.nan); out["vel"][t] = np.where(live, v, np.nan)
        out["var_level"][t] = np.where(live, Pss, np.nan); out["var_vel"][t] = np.where(live, Pvv, np.nan)
    out["loglik"] = ll; out["n_updates"] = n_upd
    return out


def fit_params(y_train: np.ndarray, td_train: np.ndarray, R_grid, q_grid):
    """Grid maximum likelihood of (R, q) on TRAIN-period series only. Returns best pair and the full table."""
    rows = []
    for R in R_grid:
        for q in q_grid:
            o = filter_series(y_train, td_train, R, q)
            rows.append((R, q, float(o["loglik"].sum() / max(o["n_updates"].sum(), 1))))
    best = max(rows, key=lambda r: r[2])
    return {"R": best[0], "q": best[1]}, rows
