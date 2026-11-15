"""M5 EDA runner: TRAINING part of the sealed hold-out only (via precursor_ml.m5_data.load_train). No model is fitted.

    ml/.venv/Scripts/python ml/scripts/m5_eda.py
Writes ml/reports/m5/results.json, tables (csv) and figures ml/reports/figures/m5/*.png. The only read that does not go through `load_train` is the
inventory-level date check requested by the user (dates and flags of the M4 event table; no features, no hold-out analysis).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from precursor_ml import m5_eda as E  # noqa: E402
from precursor_ml.m5_data import load_train, verify_seal  # noqa: E402


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def main():
    E.OUT.mkdir(parents=True, exist_ok=True)
    E.FIG.mkdir(parents=True, exist_ok=True)
    seal = verify_seal()
    rng = np.random.default_rng(E.SEED)
    cells, events, bg = load_train("5km")
    res = {"seal_sha256": seal["seal_sha256"], "seed": E.SEED, "grid": "5km", "data": "TRAINING part only"}
    res["overview"] = E.overview(cells, events, bg)
    ev_dates = pd.read_parquet(ROOT / "data/ml/processed/m4/5km/events_clean.parquet", columns=["date", "strict_all_years", "clean_strict_all_years", "clean_strict_all_years_sens"])
    res["inventory_date_structure"] = E.inventory_date_structure(ev_dates, events)
    uv = E.univariate(cells, bg, rng)
    uv.to_csv(E.OUT / "univariate_5km.csv", index=False)
    res["univariate_top20"] = uv.head(20)[["feature", "group", "auc", "auc_ci_lo", "auc_ci_hi", "cliffs_delta", "ks", "q_bh", "auc_CA_N", "auc_CA_S", "auc_OR_WA", "sign_agree_windows"]].to_dict("records")
    res["univariate_summary"] = {"features_tested": int(len(uv)), "q_bh_lt_0.05": int((uv.q_bh < 0.05).sum()), "ci_excludes_half": int(uv.ci_excludes_half.sum()), "sign_agree_all_windows": int(uv.sign_agree_windows.sum()),
                                 "max_abs_auc_minus_half": round(float(uv.abs_effect.max()), 3), "n_auc_above_0.8_or_below_0.2": int((uv.abs_effect > 0.3).sum())}
    res["physical_sanity"] = E.physical_sanity(uv)
    res["spatial"] = E.spatial_analysis(cells, events, rng)
    res["temporal"] = E.temporal_analysis(events)
    res["rainfall_percentiles"] = E.rainfall_percentiles(events)
    res["collinearity"] = E.collinearity(cells)
    res["sufficiency"] = E.sufficiency(cells, bg, events, uv, rng)
    # sensitivity: the same univariate ranking on the 10 km grid (training part)
    c10, e10, b10 = load_train("10km")
    uv10 = E.univariate(c10, b10, np.random.default_rng(E.SEED + 1), n_boot=60)
    m = uv.merge(uv10[["feature", "auc"]], on="feature", suffixes=("", "_10km"))
    res["grid_sensitivity_10km"] = {"features": int(len(m)), "train_positive_cells_10km": int((c10[~c10.excluded].label_point_count_clean_all > 0).sum()), "background_candidates_10km": int(len(b10)),
                                    "spearman_of_auc_5km_vs_10km": round(float(m.auc.corr(m.auc_10km, method="spearman")), 3),
                                    "top10_overlap": len(set(uv.feature.head(10)) & set(uv10.feature.head(10)))}
    # unknown-trigger sensitivity: label layer incl. unknown triggers vs the same background
    cs = cells.copy()
    cs["label_point_count_clean_all"] = cs.label_point_count_sens_all
    uvs = E.univariate(cs, bg[~bg.background_in_imprecise_circle], np.random.default_rng(E.SEED + 2), n_boot=60)  # also drops flagged candidates (M8 check preview)
    ms = uv.merge(uvs[["feature", "auc"]], on="feature", suffixes=("", "_sens"))
    res["sensitivity_unknown_trigger_and_unflagged_background"] = {"positive_cells": int((cs[~cs.excluded].label_point_count_clean_all > 0).sum()), "background": int((~bg.background_in_imprecise_circle).sum()),
                                                                   "spearman_of_auc_vs_primary": round(float(ms.auc.corr(ms.auc_sens, method="spearman")), 3),
                                                                   "top10_overlap": len(set(uv.feature.head(10)) & set(uvs.feature.head(10)))}
    # the two changes of the previous block, one at a time (M8 will repeat this on model results)
    uva = E.univariate(cs, bg, np.random.default_rng(E.SEED + 3), n_boot=60)  # unknown-trigger labels, all background candidates
    uvb = E.univariate(cells, bg[~bg.background_in_imprecise_circle], np.random.default_rng(E.SEED + 4), n_boot=60)  # primary labels, unflagged background only
    for name, d in (("unknown_trigger_labels_only", uva), ("unflagged_background_only", uvb)):
        mm = uv.merge(d[["feature", "auc"]], on="feature", suffixes=("", "_v"))
        res["sensitivity_unknown_trigger_and_unflagged_background"][name] = {"spearman_of_auc_vs_primary": round(float(mm.auc.corr(mm.auc_v, method="spearman")), 3),
                                                                             "top10_overlap": len(set(uv.feature.head(10)) & set(d.feature.head(10))), "built_up_auc": round(float(d[d.feature == "lc_built_up"].auc.iloc[0]), 3)}
    res["sensitivity_unknown_trigger_and_unflagged_background"]["built_up_auc_combined"] = round(float(uvs[uvs.feature == "lc_built_up"].auc.iloc[0]), 3)
    (E.OUT / "results.json").write_text(json.dumps(clean(res), indent=1))

    # ---------------------------------------------------------------- figures
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.6))
    ne = cells[~cells.excluded]
    pos = ne[ne.label_point_count_clean_all > 0]
    for a, w in zip(ax, E.WINDOWS):
        g = cells[cells.window == w]
        a.scatter(g.x_m / 1000, g.y_m / 1000, s=4, c="#d9d9d9", marker="s", linewidths=0, label="training cells (excluded cells lighter)")
        gb = bg[bg.window == w]
        a.scatter(gb.x_m / 1000, gb.y_m / 1000, s=5, c="#9ecae1", marker="s", linewidths=0, label="background candidates")
        gp = pos[pos.window == w]
        a.scatter(gp.x_m / 1000, gp.y_m / 1000, s=10 + 8 * gp.label_point_count_clean_all, c=E.COLORS[w], edgecolors="white", linewidths=0.3, label="cells with events")
        a.set_title(f"{w}: training part only (blank = not training)")
        a.set_aspect("equal")
        a.set_xlabel("x (km, UTM)")
    ax[0].legend(loc="lower left", fontsize=7, markerscale=1.2)
    fig.tight_layout()
    fig.savefig(E.FIG / "fig1_maps_train.png", dpi=130)
    plt.close(fig)

    prim = events[events.clean_strict_all_years]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    yy = prim.groupby([prim.date.dt.year, "window"]).size().unstack(fill_value=0).reindex(columns=E.WINDOWS, fill_value=0)
    bottom = np.zeros(len(yy))
    for w in E.WINDOWS:
        ax[0].bar(yy.index, yy[w], bottom=bottom, color=E.COLORS[w], label=w)
        bottom += yy[w].values
    ax[0].set_title("training events per year (primary set)")
    ax[0].legend(fontsize=7)
    mm = prim.date.dt.month.value_counts().reindex(range(1, 13), fill_value=0)
    ax[1].bar(mm.index, mm.values, color="#555555")
    ax[1].set_title("events by calendar month")
    ax[1].set_xticks(range(1, 13))
    vc = prim.date.dt.normalize().value_counts().sort_values(ascending=False).values
    ax[2].semilogy(range(1, len(vc) + 1), vc, ".", color="#555555")
    ax[2].set_title("events per date, ranked (storm clustering)")
    ax[2].set_xlabel("date rank")
    fig.tight_layout()
    fig.savefig(E.FIG / "fig2_temporal.png", dpi=130)
    plt.close(fig)

    top = uv.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 6.4))
    ax.errorbar(top.auc, range(len(top)), xerr=[top.auc - top.auc_ci_lo, top.auc_ci_hi - top.auc], fmt="o", color="#222222", capsize=2, label="pooled AUC, 95% block bootstrap")
    for w in E.WINDOWS:
        ax.scatter(top[f"auc_{w}"], range(len(top)), s=14, color=E.COLORS[w], label=w, zorder=3)
    ax.axvline(0.5, color="#999999", lw=0.8)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.feature)
    ax.set_xlabel("AUC: positive cells vs background candidates (0.5 = no difference)")
    ax.set_title("Top 20 features by |AUC - 0.5|, training part (descriptive, not performance)")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(E.FIG / "fig3_univariate_top20.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(2, 3, figsize=(12, 6))
    for a, f in zip(ax.ravel(), ["slope_mean", "rain_map_mm", "lc_built_up", "dist_river_all_mean_m", "ndvi_mean", "soil_clay_0_30"]):
        g = E.rate_by_decile(cells, f, 10)
        a.plot(g["mid"], 100 * g.rate, "o-", color="#222222")
        a.set_title(f)
        a.set_ylabel("cells with events (%)")
    fig.suptitle("Share of non-excluded training cells holding an event point, by decile of the feature")
    fig.tight_layout()
    fig.savefig(E.FIG / "fig4_deciles.png", dpi=130)
    plt.close(fig)

    v = pd.Series(res["collinearity"]["vif_top"]).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.barh(v.index, v.values, color="#555555")
    ax.axvline(10, color="#d1495b", lw=1)
    ax.set_xscale("log")
    ax.set_title("Largest VIF (after dropping composition/definition columns)")
    fig.tight_layout()
    fig.savefig(E.FIG / "fig5_vif.png", dpi=130)
    plt.close(fig)

    cur = res["sufficiency"]["univariate_auc_ci_width_vs_positive_cells"]
    xs = [cur[k]["positive_cells_in_subsample_approx"] for k in cur]
    ys = [cur[k]["median_ci_width_top5"] for k in cur]
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.plot(xs, ys, "o-", color="#222222")
    ax.set_xlabel("positive cells in the subsample")
    ax.set_ylabel("median 95% CI width of the AUC (top-5 features)")
    ax.set_title("Univariate AUC uncertainty vs sample size")
    fig.tight_layout()
    fig.savefig(E.FIG / "fig6_sufficiency.png", dpi=130)
    plt.close(fig)
    print("done; seal", seal["seal_sha256"][:12])
    print(json.dumps(clean({k: res[k] for k in ("univariate_summary", "sufficiency", "collinearity", "grid_sensitivity_10km", "sensitivity_unknown_trigger_and_unflagged_background")}), indent=1)[:3500])


if __name__ == "__main__":
    main()
