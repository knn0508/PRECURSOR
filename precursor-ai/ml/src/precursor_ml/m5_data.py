"""M5 data access: the ONLY way EDA code reads data. Returns the TRAINING part of the sealed provisional split and nothing else.

The held-out part (`split == 'heldout'`) and the gap are never returned, so exploration cannot depend on them. The seal is verified (SHA-256 of the split files
and of the manifest content) before every load.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from precursor_ml.m3 import ROOT, sha256_file
from precursor_ml.m5_split import SEAL_DIR

M4 = ROOT / "data/ml/processed/m4"
PIN = ROOT / "ml/configs/m5_seal_pin.json"


def verify_seal(seal_dir=SEAL_DIR) -> dict:
    man = json.loads((seal_dir / "split_manifest.json").read_text())
    for name, h in man["files_sha256"].items():
        if sha256_file(seal_dir / name) != h:
            raise RuntimeError(f"sealed split file changed: {name}")
    again = hashlib.sha256(json.dumps({"params": man["params"], "heldout_blocks": man["heldout_blocks"], "files": man["files_sha256"]}, sort_keys=True).encode()).hexdigest()
    if again != man["seal_sha256"]:
        raise RuntimeError("seal hash mismatch")
    pinned = json.loads(PIN.read_text())["seal_sha256"]
    if man["seal_sha256"] != pinned:
        raise RuntimeError("seal differs from the pinned seal (ml/configs/m5_seal_pin.json)")
    return man


def train_only(df: pd.DataFrame) -> pd.DataFrame:
    out = df[df["split"].eq("train")].copy()
    assert out["split"].eq("train").all()
    return out


def load_train(grid: str = "5km"):
    """(cells_train, events_train, background_train): training rows only, with the cell/event split columns dropped after filtering."""
    verify_seal()
    cs = pd.read_parquet(SEAL_DIR / f"cell_split_{grid}.parquet")
    es = pd.read_parquet(SEAL_DIR / "event_split.parquet")
    allc = pd.read_parquet(M4 / grid / "cells_clean.parquet").merge(cs, on=["window", "row", "col"], how="left", validate="one_to_one")
    cells = train_only(allc)
    events = train_only(pd.read_parquet(M4 / grid / "events_clean.parquet").merge(es, on=["window", "event_id"], how="left", validate="one_to_one"))
    bgr = pd.read_parquet(M4 / grid / "background_candidates.parquet").merge(cs, on=["window", "row", "col"], how="left", validate="one_to_one")
    bgr = train_only(bgr)  # filter BEFORE attaching features: held-out/gap candidates never reach the caller
    feats = allc.drop(columns=[c for c in allc.columns if c in bgr.columns and c not in ("window", "row", "col")])
    bg = bgr.merge(feats, on=["window", "row", "col"], how="left", validate="one_to_one")
    return cells, events, bg
