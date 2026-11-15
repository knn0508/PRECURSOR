"""Seal the provisional spatial hold-out (run ONCE, before any M5 exploration). Refuses to overwrite an existing seal.
    ml/.venv/Scripts/python ml/scripts/m5_seal.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m5_split  # noqa: E402

if (m5_split.SEAL_DIR / "split_manifest.json").exists():
    print("a seal already exists; it is never overwritten:", m5_split.SEAL_DIR)
    sys.exit(2)
M4 = ROOT / "data/ml/processed/m4"
import json  # noqa: E402

old = ROOT / "data/ml/splits/superseded/m5_provisional_holdout_v1_gap20km/SUPERSEDED.json"
man = m5_split.seal(M4 / "5km/cells_clean.parquet", M4 / "10km/cells_clean.parquet", M4 / "5km/events_clean.parquet", supersedes=json.loads(old.read_text()) if old.exists() else None)
print("sealed", man["seal_sha256"])
for w, i in man["blocks_info"].items():
    if w in ("OR_WA", "CA_N", "CA_S"):
        print(w, i)
print("primary clean strict events by split (counts only):", man["blocks_info"]["primary_clean_strict_events_by_split"])
