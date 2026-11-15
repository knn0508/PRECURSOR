"""M5 exploratory data analysis on the TRAINING part of the sealed provisional split ONLY (ML track, ADR-0009).

Data come exclusively from `precursor_ml.m5_data.load_train`; the held-out part and the gap are never read here (a test scans this file for the forbidden
tokens). No model is fitted: the only fits are univariate rank statistics and a linear-algebra VIF, none reported as performance. P-values are descriptive:
spatially autocorrelated cells and clustered events make them anti-conservative, so block-bootstrap intervals are given next to them.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse, stats
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform

from precursor_ml import m3, m4
from precursor_ml.m3 import ROOT
from precursor_ml.m5_data import load_train

OUT = ROOT / "ml/reports/m5"
FIG = ROOT / "ml/reports/figures/m5"
SEED = 20261117
BLOCK_M = 50_000
WINDOWS = ["CA_N", "CA_S", "OR_WA"]
COLORS = {"CA_N": "#2a6f97", "CA_S": "#d1495b", "OR_WA": "#3d8361"}
# expected sign of the association with landslide presence (AUC above 0.5 = higher in positive cells); only features with a clear physical expectation
EXPECTED = {"slope_mean": "+", "slope_q3": "+", "slope_max": "+", "slope_frac_gt15": "+", "slope_frac_gt30": "+", "relief": "+", "elev_std": "+", "rain_map_mm": "+",
            "rain_djf_mm": "+", "rain_max_month_clim_mm": "+", "dist_river_all_mean_m": "-", "dist_river_major_mean_m": "-", "soil_clay_0_30": "+", "lc_built_up": "+"}


# ---------------------------------------------------------------------------------------------- statistics helpers
def auc_rank(pos: np.ndarray, neg: np.ndarray) -> float:
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if len(pos) < 5 or len(neg) < 5:
        return float("nan")
    r = stats.rankdata(np.concatenate([pos, neg]))
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def bh_fdr(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in zip(range(n, 0, -1), order[::-1]):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q


def block_key(df: pd.DataFrame) -> np.ndarray:
    return (df.window.astype(str) + "_" + (df.x_m // BLOCK_M).astype(int).astype(str) + "_" + (df.y_m // BLOCK_M).astype(int).astype(str)).values


def block_bootstrap_auc(pos: pd.DataFrame, neg: pd.DataFrame, feats: list[str], n_boot: int, rng) -> dict:
    """95% interval of the AUC when whole 50 km blocks are resampled (accounts for spatial dependence)."""
    pb, nb = block_key(pos), block_key(neg)
    blocks = np.unique(np.concatenate([pb, nb]))
    ip = {b: np.where(pb == b)[0] for b in blocks}
    ineg = {b: np.where(nb == b)[0] for b in blocks}
    pv, nv = {f: pos[f].values for f in feats}, {f: neg[f].values for f in feats}
    res = {f: [] for f in feats}
    for _ in range(n_boot):
        pick = rng.choice(blocks, size=len(blocks), replace=True)
        a = np.concatenate([ip[b] for b in pick])
        c = np.concatenate([ineg[b] for b in pick])
        if len(a) < 20 or len(c) < 20:
            continue
        for f in feats:
            res[f].append(auc_rank(pv[f][a], nv[f][c]))
    return {f: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))) if len(v) > 20 else (float("nan"), float("nan")) for f, v in res.items()}


# ---------------------------------------------------------------------------------------------- 1. overview
def overview(cells, events, bg):
    ne = cells[~cells.excluded]
    pos = ne[ne.label_point_count_clean_all > 0]
    prim = events[events.clean_strict_all_years]
    sens = events[events.clean_strict_all_years_sens]
    rows = {}
    for w in WINDOWS:
        c, p, e = ne[ne.window == w], pos[pos.window == w], prim[prim.window == w]
        rows[w] = {"train_cells": int((cells.window == w).sum()), "train_cells_nonexcluded": int(len(c)), "train_cells_excluded": int(((cells.window == w) & cells.excluded).sum()),
                   "positive_cells": int(len(p)), "positive_cell_rate_vs_nonexcluded": round(len(p) / max(len(c), 1), 4),
                   "events_primary": int(len(e)), "events_sensitivity_incl_unknown_trigger": int((sens.window == w).sum()),
                   "events_in_excluded_cells": int((e.in_excluded_cell).sum()), "background_candidates": int((bg.window == w).sum()),
                   "background_flagged_imprecise_circle": int(bg[bg.window == w].background_in_imprecise_circle.sum())}
    yrs = prim.groupby([prim.date.dt.year, "window"]).size().unstack(fill_value=0)
    feats = m4.feature_columns(cells)
    miss = ne.groupby("window")[feats].apply(lambda g: g.isna().mean()).T
    grp = pd.Series({f: m4.group_of(f) for f in feats})
    miss_g = miss.groupby(grp).mean().round(3)
    return {"per_window": rows, "events_per_year_by_window": yrs.to_dict("index"), "missing_share_by_group_window_nonexcluded": miss_g.to_dict(),
            "totals": {"train_cells": int(len(cells)), "train_positive_cells": int(len(pos)), "train_events_primary": int(len(prim)), "train_events_sensitivity": int(len(sens)),
                       "train_background_candidates": int(len(bg))}}


def inventory_date_structure(events_all: pd.DataFrame, events_train: pd.DataFrame) -> dict:
    """Inventory-level check of the earlier claims (dates only; no feature, no hold-out analysis). `events_all` = M4 event table (all rows)."""
    out = {}
    for name, ev in (("M3_strict_667", events_all[events_all.strict_all_years]), ("M4_clean_strict_647", events_all[events_all.clean_strict_all_years]),
                     ("M4_sensitivity_976_incl_unknown_trigger", events_all[events_all.clean_strict_all_years_sens]), ("train_part_primary", events_train[events_train.clean_strict_all_years])):
        d = ev.date.dt.normalize()
        vc = d.value_counts()
        out[name] = {"events": int(len(ev)), "distinct_dates": int(d.nunique()), "events_in_2017": int((ev.date.dt.year == 2017).sum()), "events_in_2010_2011": int(ev.date.dt.year.isin([2010, 2011]).sum()),
                     "top5_dates": {str(k.date()): int(v) for k, v in vc.head(5).items()}, "share_on_top10_dates": round(float(vc.head(10).sum() / len(ev)), 3),
                     "dates_with_5_or_more_events": int((vc >= 5).sum()), "events_on_dates_with_5_or_more": int(vc[vc >= 5].sum()), "events_by_year": {int(k): int(v) for k, v in ev.date.dt.year.value_counts().sort_index().items()}}
    return out


# ---------------------------------------------------------------------------------------------- 2. univariate / bivariate
def univariate(cells, bg, rng, n_boot=200):
    ne = cells[~cells.excluded]
    pos = ne[ne.label_point_count_clean_all > 0]
    feats = m4.feature_columns(cells)
    neg = bg
    rows = []
    for f in feats:
        a, b = pos[f].dropna().values, neg[f].dropna().values
        if len(a) < 5 or len(b) < 5 or np.nanstd(np.concatenate([a, b])) == 0:
            continue
        u = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        auc = auc_rank(a, b)
        ks = stats.ks_2samp(a, b).statistic
        row = {"feature": f, "group": m4.group_of(f), "n_pos": int(len(a)), "n_bg": int(len(b)), "auc": auc, "cliffs_delta": 2 * auc - 1, "ks": float(ks), "p_mwu": float(u.pvalue),
               "median_pos": float(np.median(a)), "median_bg": float(np.median(b))}
        for w in WINDOWS:
            row[f"auc_{w}"] = auc_rank(pos[pos.window == w][f].values, neg[neg.window == w][f].values)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["q_bh"] = bh_fdr(df.p_mwu.values)
    ci = block_bootstrap_auc(pos, neg, df.feature.tolist(), n_boot, rng)
    df["auc_ci_lo"] = [ci[f][0] for f in df.feature]
    df["auc_ci_hi"] = [ci[f][1] for f in df.feature]
    df["abs_effect"] = (df.auc - 0.5).abs()
    wins = df[[f"auc_{w}" for w in WINDOWS]]
    df["sign_agree_windows"] = ((wins - 0.5).apply(np.sign).abs().sum(axis=1) == 3) & ((wins - 0.5).apply(np.sign).nunique(axis=1) == 1)
    df["ci_excludes_half"] = (df.auc_ci_lo > 0.5) | (df.auc_ci_hi < 0.5)
    return df.sort_values("abs_effect", ascending=False).reset_index(drop=True)


def physical_sanity(uv: pd.DataFrame) -> list[dict]:
    out = []
    for f, sign in EXPECTED.items():
        r = uv[uv.feature == f]
        if r.empty:
            continue
        r = r.iloc[0]
        ok = (r.auc > 0.5) if sign == "+" else (r.auc < 0.5)
        per = {w: bool((r[f"auc_{w}"] > 0.5) == (sign == "+")) for w in WINDOWS}
        out.append({"feature": f, "expected": sign, "auc": round(float(r.auc), 3), "ci": [round(float(r.auc_ci_lo), 3), round(float(r.auc_ci_hi), 3)], "as_expected_pooled": bool(ok),
                    "as_expected_by_window": per, "flag": "" if ok and all(per.values()) else "SURPRISE: check for artifact, confounding or reporting bias"})
    return out


def rate_by_decile(cells, f, q=10):
    ne = cells[~cells.excluded & cells[f].notna()].copy()
    ne["bin"] = pd.qcut(ne[f].rank(method="first"), q, labels=False)
    g = ne.groupby("bin").agg(rate=("label_point_count_clean_all", lambda s: float((s > 0).mean())), mid=(f, "median"), n=(f, "size"))
    return g


# ---------------------------------------------------------------------------------------------- 3. spatial
def morans_i(df: pd.DataFrame, var: str, rng, n_perm=999) -> dict:
    """Queen-contiguity Moran's I on the grid cells present in `df` (one window); permutation p-value."""
    idx = {(r, c): i for i, (r, c) in enumerate(zip(df["row"].values, df["col"].values))}
    ii, jj = [], []
    for (r, c), i in idx.items():
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr or dc) and (r + dr, c + dc) in idx:
                    ii.append(i)
                    jj.append(idx[(r + dr, c + dc)])
    n = len(df)
    W = sparse.csr_matrix((np.ones(len(ii)), (ii, jj)), shape=(n, n))
    rs = np.asarray(W.sum(1)).ravel()
    W = sparse.diags(1 / np.maximum(rs, 1)) @ W
    z = df[var].values.astype(float)
    ok = np.isfinite(z)
    if ok.sum() < 30:
        return {"I": None, "p": None, "n": int(ok.sum())}
    z = np.where(ok, z, np.nanmean(z))
    z = z - z.mean()
    s0 = W.sum()
    stat = lambda v: float((n / s0) * (v @ (W @ v)) / (v @ v))  # noqa: E731
    obs = stat(z)
    perm = np.array([stat(rng.permutation(z)) for _ in range(n_perm)])
    return {"I": round(obs, 4), "expected_I": round(-1 / (n - 1), 4), "p_perm": float((1 + (perm >= obs).sum()) / (n_perm + 1)), "n": int(n)}


def spatial_analysis(cells, events, rng):
    ne = cells[~cells.excluded].copy()
    ne["pos"] = (ne.label_point_count_clean_all > 0).astype(float)
    mor = {}
    for w in WINDOWS:
        g = ne[ne.window == w]
        mor[w] = {v: morans_i(g, v, rng) for v in ("pos", "slope_mean", "rain_map_mm", "ndvi_mean")}
    prim = events[events.clean_strict_all_years]
    ce = {}
    for w in WINDOWS:
        e = prim[prim.window == w]
        pts = np.unique(np.round(e[["x_m", "y_m"]].values / 100) * 100, axis=0)
        if len(pts) < 5:
            continue
        d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
        np.fill_diagonal(d, np.inf)
        nn = d.min(1)
        area = float((cells.window == w).sum()) * (m3.load_config()["grid"]["cell_m"] ** 2)  # train cells only (area available to the events)
        dens = len(pts) / area
        ce[w] = {"events": int(len(e)), "distinct_points": int(len(pts)), "mean_nn_m": round(float(nn.mean()), 1), "clark_evans_R": round(float(nn.mean() / (0.5 / math.sqrt(dens))), 3),
                 "share_within_5km_of_another": round(float((nn <= 5000).mean()), 3), "share_within_10km": round(float((nn <= 10000).mean()), 3), "share_within_20km": round(float((nn <= 20000).mean()), 3)}
    # reporting bias: positive-cell rate by built-up share and by river distance (roads are not available)
    bias = {}
    for f in ("lc_built_up", "dist_river_all_mean_m"):
        g = rate_by_decile(cells, f, 5)
        bias[f] = {"rate_by_quintile": [round(float(x), 4) for x in g.rate], "median_by_quintile": [round(float(x), 4) for x in g["mid"]]}
    return {"morans_I_5km": mor, "event_clustering": ce, "reporting_bias_proxies": bias}


# ---------------------------------------------------------------------------------------------- 4. temporal
def temporal_analysis(events, thresholds=(150, 40)):
    prim = events[events.clean_strict_all_years].copy()
    mon = prim.date.dt.month.value_counts().sort_index()
    seas = {"events_by_month": {int(k): int(v) for k, v in mon.items()}, "share_DJF": round(float(prim.date.dt.month.isin([12, 1, 2]).mean()), 3),
            "share_Nov_to_Mar": round(float(prim.date.dt.month.isin([11, 12, 1, 2, 3]).mean()), 3)}
    feas = {}
    for cut in range(2009, 2017):
        a, b = prim[prim.date <= f"{cut}-12-31 23:59"], prim[prim.date > f"{cut}-12-31 23:59"]
        feas[cut] = {"train_events": int(len(a)), "train_dates": int(a.date.dt.normalize().nunique()), "test_events": int(len(b)), "test_dates": int(b.date.dt.normalize().nunique()),
                     "meets_criteria": bool(len(a) >= thresholds[0] and len(b) >= thresholds[0] and a.date.dt.normalize().nunique() >= thresholds[1] and b.date.dt.normalize().nunique() >= thresholds[1])}
    byyear = prim.date.dt.year.value_counts().sort_index()
    yrs = byyear.index.values
    slope = stats.linregress(yrs, byyear.values) if len(yrs) > 3 else None
    return {"seasonality": seas, "temporal_holdout_feasibility_train_part_only": {"criteria": f">= {thresholds[0]} events and >= {thresholds[1]} distinct dates on EACH side", "by_cutoff_year_end": feas},
            "events_by_year": {int(k): int(v) for k, v in byyear.items()}, "trend_events_per_year_slope": None if slope is None else round(float(slope.slope), 2),
            "note": "the GLC compiles news reports starting in 2007: a rise in counts reflects reporting effort and storms as much as landslide frequency (non-stationarity)"}


def rainfall_percentiles(events, series_dir=m3.INTERIM):
    """Percentile of the rainfall of the month BEFORE the event month within the same calendar month across 2002-2017 at the event's IMERG cell (training events)."""
    prim = events[events.clean_strict_all_years & (events.date >= "2002-02-01") & (events.date <= "2017-12-31")]
    pct = []
    for w in WINDOWS:
        z = np.load(series_dir / w / "imerg_monthly.npz")
        P, months, lon, lat = z["precip_mm_month"], [pd.Timestamp(m) for m in z["month_start_utc"]], z["lon"], z["lat"]
        idx = {(m.year, m.month): k for k, m in enumerate(months)}
        for _, r in prim[prim.window == w].iterrows():
            pm = (r.date.year - (r.date.month == 1), 12 if r.date.month == 1 else r.date.month - 1)
            if pm not in idx:
                continue
            j, i = int(np.argmin(np.abs(lat - r.latitude))), int(np.argmin(np.abs(lon - r.longitude)))
            ref = np.array([P[idx[(y, pm[1])], j, i] for y in range(2002, 2018) if (y, pm[1]) in idx])
            if len(ref) >= 10:
                pct.append({"window": w, "pct": float((ref <= P[idx[pm], j, i]).mean())})
    d = pd.DataFrame(pct)
    if d.empty:
        return {}
    w = stats.wilcoxon(d.pct - 0.5)
    return {"events": int(len(d)), "median_percentile_of_prior_month_rain": round(float(d.pct.median()), 3), "share_above_75th": round(float((d.pct > 0.75).mean()), 3),
            "share_above_90th": round(float((d.pct > 0.90).mean()), 3), "wilcoxon_p_vs_median_0.5": float(w.pvalue),
            "by_window_median": {k: round(float(v), 3) for k, v in d.groupby("window").pct.median().items()},
            "null": "uniform percentiles (median 0.5); events are clustered in few storms, so the p-value is descriptive only"}


# ---------------------------------------------------------------------------------------------- 5. collinearity
def collinearity(cells, thr=0.9):
    ne = cells[~cells.excluded]
    feats = m4.feature_columns(cells)
    X = ne[feats].copy()
    X = X.loc[:, X.std() > 0]
    rho = X.corr(method="spearman", min_periods=200)
    dist = 1 - rho.abs().fillna(0).values
    np.fill_diagonal(dist, 0)
    Z = hierarchy.linkage(squareform(np.clip(dist, 0, None), checks=False), "average")
    lab = hierarchy.fcluster(Z, t=1 - thr, criterion="distance")
    clusters = {}
    for f, c in zip(X.columns, lab):
        clusters.setdefault(int(c), []).append(f)
    multi = [v for v in clusters.values() if len(v) > 1]
    single_depths = {f for f in X.columns if f.startswith("soil_") and not f.endswith("_0_30") and f != "soil_cover"}  # the 0-30 cm mean is an exact linear mix of the three depths
    drop = {"lc_tree_cover", "lith_UNCONSOLIDATED", "soil_silt_0_30", "lc_valid_frac", "lith_cover", "soil_cover", "dem_cover", "ndvi_valid_month_share", "relief"} | single_depths
    v = ne[[f for f in X.columns if f not in drop]].dropna()
    v = (v - v.mean()) / v.std()
    C = np.corrcoef(v.values.T)
    try:
        vif = np.diag(np.linalg.inv(C))
    except np.linalg.LinAlgError:
        vif = np.diag(np.linalg.pinv(C))
    vif_s = pd.Series(vif, index=v.columns).sort_values(ascending=False)
    return {"n_features": int(X.shape[1]), "abs_spearman_threshold": thr, "redundancy_clusters_gt1": multi, "n_clusters": int(len(clusters)),
            "vif_complete_cases": int(len(v)), "vif_features": int(v.shape[1]), "vif_dropped_for_composition_or_definition": sorted(drop & set(X.columns)),
            "vif_top": {k: round(float(x), 1) for k, x in vif_s.head(15).items()}, "features_vif_gt10": int((vif_s > 10).sum()), "features_vif_gt100": int((vif_s > 100).sum())}


# ---------------------------------------------------------------------------------------------- 7. sufficiency
def sufficiency(cells, bg, events, uv, rng):
    ne = cells[~cells.excluded]
    pos = ne[ne.label_point_count_clean_all > 0]
    prim = events[events.clean_strict_all_years]
    occ_blocks = len(set(block_key(pos)))
    ev_blocks = len(set(block_key(prim)))
    n_ev, n_pos = int(len(prim)), int(len(pos))
    eff = {"train_events": n_ev, "train_positive_cells": n_pos, "occupied_50km_blocks_with_positives": int(occ_blocks), "occupied_50km_blocks_with_events": int(ev_blocks),
           "distinct_event_dates": int(prim.date.dt.normalize().nunique()), "events_per_variable_if_72_features": round(n_ev / 72, 1), "events_per_variable_if_15_features": round(n_ev / 15, 1),
           "positive_cells_per_variable_if_15_features": round(n_pos / 15, 1)}
    top = uv.feature.head(5).tolist()
    pos_b, neg_b = block_key(pos), block_key(bg)
    blocks = np.unique(np.concatenate([pos_b, neg_b]))
    curve = {}
    for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
        widths = {f: [] for f in top}
        for _ in range(8):
            sub = rng.choice(blocks, size=max(3, int(frac * len(blocks))), replace=False)
            sp, sn = pos[np.isin(pos_b, sub)], bg[np.isin(neg_b, sub)]
            if len(sp) < 8 or len(sn) < 8:
                continue
            ci = block_bootstrap_auc(sp, sn, top, 40, rng)
            for f in top:
                widths[f].append(ci[f][1] - ci[f][0])
        curve[frac] = {"positive_cells_in_subsample_approx": int(frac * n_pos), "median_ci_width_top5": round(float(np.nanmedian([np.nanmedian(v) for v in widths.values() if v])), 3)}
    xs = np.array([curve[f]["positive_cells_in_subsample_approx"] for f in curve], float)
    ys = np.array([curve[f]["median_ci_width_top5"] for f in curve], float)
    ok = np.isfinite(ys) & (xs > 0)
    k = float(np.exp(np.mean(np.log(ys[ok]) + 0.5 * np.log(xs[ok])))) if ok.any() else float("nan")  # width ~ k / sqrt(n)
    eff["univariate_auc_ci_width_vs_positive_cells"] = curve
    eff["width_fit_k_over_sqrt_n"] = round(k, 2)
    eff["positive_cells_for_ci_width_0.10"] = int((k / 0.10) ** 2) if np.isfinite(k) else None
    return eff
