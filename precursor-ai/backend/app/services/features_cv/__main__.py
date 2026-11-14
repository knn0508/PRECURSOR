"""CLI: python -m app.services.features_cv extract|dataset --area-id <uuid>   (run from backend/). Files only; no network."""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from app.core.config import get_settings
from app.services.features_cv.dataset import DatasetParams
from app.services.features_cv.dataset_run import EVENTS_ORIGINS, run_dataset
from app.services.features_cv.events import load_events
from app.services.features_cv.pipeline import run_extraction
from app.services.features_cv.types import FeatureError, NotAvailable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="features_cv", description="Phase 5 feature extraction and labelled dataset (no ML)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="extract feature rasters from the Phase 4 aligned stack")
    e.add_argument("--area-id", required=True, type=uuid.UUID)
    e.add_argument("--normalise", choices=["zscore", "minmax"], default=None, help="record normalisation parameters per feature")
    d = sub.add_parser("dataset", help="build the labelled sample dataset from catalog events")
    d.add_argument("--area-id", required=True, type=uuid.UUID)
    d.add_argument("--seed", type=int, default=0)
    d.add_argument("--background-ratio", type=float, default=1.0)
    d.add_argument("--block-m", type=float, default=None)
    d.add_argument("--events-origin", choices=EVENTS_ORIGINS, default="UNKNOWN")
    a = ap.parse_args(argv)
    root = get_settings().data_root
    try:
        if a.cmd == "extract":
            m = run_extraction(root, a.area_id, normalise=a.normalise)
            print(json.dumps({"features_done": m["counts"]["done"], "not_available": m["counts"]["not_available"], "synthetic": m["contains_synthetic_data"]}))
        else:
            from app.database.session import SessionLocal  # noqa: PLC0415  (DB only needed here)

            with SessionLocal() as db:
                events = load_events(db, a.area_id)
            m = run_dataset(root, a.area_id, events, DatasetParams(seed=a.seed, background_ratio=a.background_ratio, block_m=a.block_m), events_origin=a.events_origin)
            print(json.dumps({"counts": m["counts"], "leakage_ok": m["leakage"]["ok"], "synthetic": m["contains_synthetic_data"]}))
    except (FeatureError, NotAvailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
