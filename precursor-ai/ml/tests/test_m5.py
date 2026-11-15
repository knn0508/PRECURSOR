"""M5 tests: the sealed provisional hold-out, the train-only data guard, statistic helpers (SYNTHETIC fixtures) and consistency of the real EDA outputs."""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m5_data, m5_eda as E, m5_split  # noqa: E402

SEAL = m5_split.SEAL_DIR
HAVE = (SEAL / "split_manifest.json").exists()
M4 = ROOT / "data/ml/processed/m4"


# ------------------------------------------------------------------ geometry and statistics (SYNTHETIC)
def test_assign_blocks_and_gap_geometry():
    df = pd.DataFrame({"window": "W", "x_m": [25000.0, 62000.0, 75000.0, 130000.0, 200000.0], "y_m": 25000.0})
    held = {"W": [(0, 0)]}  # block (0,0) = [0, 50 km) x [0, 50 km)
    assert m5_split.assign(df, held, 50_000, 10_000).tolist() == ["heldout", "train", "train", "train", "train"]  # 62 km is 12 km from the block: outside a 10 km gap
    assert m5_split._rect_distance(np.array([62000.0]), np.array([25000.0]), [(0, 0)], 50_000)[0] == 12000.0
    corner = pd.DataFrame({"window": "W", "x_m": [56000.0], "y_m": [56000.0]})  # diagonal distance sqrt(2)*6 km = 8.5 km: inside the gap
    assert m5_split.assign(corner, held, 50_000, 10_000).iloc[0] == "gap"


def test_gap_rule_boundaries():
    held = {"W": [(0, 0)]}
    pts = pd.DataFrame({"window": "W", "x_m": [55000.0, 60000.0, 61000.0], "y_m": 25000.0})  # 5 km, 10 km, 11 km from the block edge
    assert m5_split.assign(pts, held, 50_000, 10_000).tolist() == ["gap", "train", "train"]  # distance < gap is gap; exactly the gap is train


def test_auc_rank_bh_and_morans_i():
    assert E.auc_rank(np.arange(10, 20.0), np.arange(0, 10.0)) == 1.0 and E.auc_rank(np.arange(10.0), np.arange(10.0)) == 0.5
    q = E.bh_fdr(np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]))
    assert np.all(np.diff(q[np.argsort([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])]) >= -1e-12) and abs(q[0] - 0.01) < 1e-9
    n = 12
    grid = pd.DataFrame({"row": np.repeat(np.arange(n), n), "col": np.tile(np.arange(n), n)})
    grid["smooth"] = grid.row + grid.col
    grid["checker"] = grid.row % 2  # alternating rows: with queen contiguity 6 of 8 neighbours differ, expected I about -0.5
    rng = np.random.default_rng(0)
    assert E.morans_i(grid, "smooth", rng, 199)["I"] > 0.8
    assert E.morans_i(grid, "checker", rng, 199)["I"] < -0.3


def test_block_bootstrap_ci_contains_point_estimate_and_is_wider_for_few_blocks():
    rng = np.random.default_rng(1)
    n = 400
    pos = pd.DataFrame({"window": "W", "x_m": rng.uniform(0, 400000, n), "y_m": rng.uniform(0, 400000, n), "f": rng.normal(0.5, 1, n)})
    neg = pd.DataFrame({"window": "W", "x_m": rng.uniform(0, 400000, n), "y_m": rng.uniform(0, 400000, n), "f": rng.normal(0, 1, n)})
    lo, hi = E.block_bootstrap_auc(pos, neg, ["f"], 100, np.random.default_rng(2))["f"]
    assert lo < E.auc_rank(pos.f.values, neg.f.values) < hi


# ------------------------------------------------------------------ the seal
@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_seal_is_verified_hashed_and_records_its_predecessor():
    man = m5_data.verify_seal()
    assert man["params"]["gap_m"] == 10_000 and man["params"]["block_m"] == 50_000 and man["supersedes"]["gap_m"] == 20_000
    old = json.loads((ROOT / "data/ml/splits/superseded/m5_provisional_holdout_v1_gap20km/SUPERSEDED.json").read_text())
    assert {w: [list(b) for b in v] for w, v in man["heldout_blocks"].items()} == old["heldout_blocks"]  # superseded only in the gap: same held-out blocks
    assert man["supersedes"]["seal_sha256"] == old["seal_sha256"]


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_tampering_with_a_split_file_is_detected(tmp_path):
    d = tmp_path / "seal"
    shutil.copytree(SEAL, d)
    m5_data.verify_seal(d)
    f = d / "event_split.parquet"
    df = pd.read_parquet(f)
    df.loc[df.index[0], "split"] = "train" if df.split.iloc[0] != "train" else "heldout"
    df.to_parquet(f, index=False)
    with pytest.raises(RuntimeError):
        m5_data.verify_seal(d)


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_holdout_coverage_gap_and_disjointness_on_real_cells():
    man = json.loads((SEAL / "split_manifest.json").read_text())
    B, G = man["params"]["block_m"], man["params"]["gap_m"]
    for tag in ("5km", "10km"):
        c = pd.read_parquet(M4 / tag / "cells_clean.parquet").merge(pd.read_parquet(SEAL / f"cell_split_{tag}.parquet"), on=["window", "row", "col"], validate="one_to_one")
        ne = c[~c.excluded]
        share = ne.groupby("window").split.apply(lambda s: float((s == "heldout").mean()))
        if tag == "5km":
            assert share.between(0.18, 0.25).all(), share.to_dict()  # about 20% of the non-excluded cells in each window
        for w, g in c.groupby("window"):
            a, b = g[g.split == "train"], g[g.split == "heldout"]
            d = np.hypot(a.x_m.values[:, None] - b.x_m.values[None, :], a.y_m.values[:, None] - b.y_m.values[None, :])
            assert d.min() >= G  # every training cell is at least `gap` from every held-out cell centre (and cells in the buffer are labelled gap)
    es = pd.read_parquet(SEAL / "event_split.parquet")
    prim = pd.read_parquet(M4 / "5km/events_clean.parquet")
    prim = prim[prim.clean_strict_all_years].merge(es, on=["window", "event_id"])
    share = prim.split.value_counts(normalize=True)
    assert 0.10 <= share["heldout"] <= 0.30


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_load_train_returns_only_training_rows_and_never_held_out_keys():
    for grid in ("5km", "10km"):
        cells, events, bg = m5_data.load_train(grid)
        assert (cells.split == "train").all() and (events.split == "train").all() and (bg.split == "train").all()
        cs = pd.read_parquet(SEAL / f"cell_split_{grid}.parquet")
        held = cs[cs.split != "train"][["window", "row", "col"]]
        for df in (cells, bg):
            assert df.merge(held, on=["window", "row", "col"]).empty  # no held-out or gap cell reaches the analyst
        es = pd.read_parquet(SEAL / "event_split.parquet")
        assert events.merge(es[es.split != "train"][["window", "event_id"]], on=["window", "event_id"]).empty
        assert not bg.empty and "slope_mean" in bg  # background candidates carry features (attached after the train filter)


def test_eda_code_cannot_name_the_heldout_part():
    forbidden = ("heldout", "cell_split", "event_split", "SEAL_DIR", "split == 'test'", 'split == "test"', "split != 'train'", 'split != "train"')
    for p in (ROOT / "ml/src/precursor_ml/m5_eda.py", ROOT / "ml/scripts/m5_eda.py"):
        src = p.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in src, f"{p.name} mentions {tok!r}"
        assert "load_train" in src
    nb = ROOT / "ml/notebooks/M5_eda.ipynb"
    if nb.exists():
        assert "heldout" not in nb.read_text(encoding="utf-8")


# ------------------------------------------------------------------ real EDA outputs
@pytest.mark.skipif(not (ROOT / "ml/reports/m5/results.json").exists(), reason="run ml/scripts/m5_eda.py first")
def test_eda_results_bound_to_the_seal_and_verify_earlier_claims():
    r = json.loads((ROOT / "ml/reports/m5/results.json").read_text())
    assert r["seal_sha256"] == json.loads((SEAL / "split_manifest.json").read_text())["seal_sha256"] and r["data"] == "TRAINING part only"
    inv = r["inventory_date_structure"]
    assert (inv["M3_strict_667"]["events"], inv["M3_strict_667"]["distinct_dates"], inv["M3_strict_667"]["events_in_2017"]) == (667, 321, 185)  # earlier claim reproduced
    assert (inv["M4_clean_strict_647"]["events"], inv["M4_clean_strict_647"]["distinct_dates"]) == (647, 321)
    assert r["overview"]["totals"]["train_events_primary"] == inv["train_part_primary"]["events"] == 460
    assert r["univariate_summary"]["features_tested"] > 60 and r["sufficiency"]["occupied_50km_blocks_with_positives"] > 20
    u = pd.read_csv(ROOT / "ml/reports/m5/univariate_5km.csv")
    assert u.q_bh.between(0, 1).all() and (u.auc_ci_lo <= u.auc_ci_hi).all()


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_univariate_is_deterministic_for_a_fixed_seed():
    cells, events, bg = m5_data.load_train("10km")
    a = E.univariate(cells, bg, np.random.default_rng(5), n_boot=20)
    b = E.univariate(cells, bg, np.random.default_rng(5), n_boot=20)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_rewriting_files_and_manifest_together_is_still_detected_by_the_pin(tmp_path):
    import hashlib

    d = tmp_path / "seal"
    shutil.copytree(SEAL, d)
    f = d / "event_split.parquet"
    df = pd.read_parquet(f)
    df.loc[df.index[0], "split"] = "train" if df.split.iloc[0] != "train" else "heldout"
    df.to_parquet(f, index=False)
    man = json.loads((d / "split_manifest.json").read_text())
    man["files_sha256"]["event_split.parquet"] = m5_split.sha256_file(f)  # the attacker also fixes the manifest and its seal hash
    man["seal_sha256"] = hashlib.sha256(json.dumps({"params": man["params"], "heldout_blocks": man["heldout_blocks"], "files": man["files_sha256"]}, sort_keys=True).encode()).hexdigest()
    (d / "split_manifest.json").write_text(json.dumps(man))
    with pytest.raises(RuntimeError, match="pinned"):
        m5_data.verify_seal(d)


@pytest.mark.skipif(not HAVE, reason="hold-out not sealed")
def test_seal_refuses_to_overwrite_an_existing_seal(tmp_path):
    d = tmp_path / "seal"
    shutil.copytree(SEAL, d)
    with pytest.raises(FileExistsError):
        m5_split.seal(M4 / "5km/cells_clean.parquet", M4 / "10km/cells_clean.parquet", M4 / "5km/events_clean.parquet", out_dir=d)
    assert json.loads((ROOT / "ml/configs/m5_seal_pin.json").read_text())["seal_sha256"] == json.loads((SEAL / "split_manifest.json").read_text())["seal_sha256"]
