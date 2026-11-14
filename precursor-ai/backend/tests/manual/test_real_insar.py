"""MANUAL real-data check for Phase 3. Skipped unless you point it at a real, already-downloaded file:

    REAL_INSAR_FILE=/absolute/path/to/NISAR_L2_..._GUNW_....h5 pytest tests/manual/test_real_insar.py -s

It never downloads anything and never needs Earthdata credentials. It inspects the actual product, runs ONLY the
stages that the product's own metadata supports, and prints an explicit validation verdict. Passing means the
pipeline ran on that file; it does NOT mean the output is scientifically validated (sign convention, reference
point and atmospheric error still need an independent check against known motion).
"""
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.insar import synthetic  # noqa: F401  (imported so a missing dependency fails loudly)
from app.services.insar.inspection import inspect_product
from app.services.insar.processing import process_gunw, quality_report
from app.services.insar.types import DataOrigin, ProcessingConfig, ProductKind, ProductType

FILE = os.getenv("REAL_INSAR_FILE")
pytestmark = pytest.mark.skipif(not FILE, reason="manual real-data test: set REAL_INSAR_FILE to a downloaded product")


def test_real_file_inspection_and_supported_processing(tmp_path):
    path = Path(FILE)
    assert path.is_file(), "REAL_INSAR_FILE must be an existing local file"
    rep = inspect_product(path, DataOrigin.LOCAL_UNVERIFIED)
    print("\nPRODUCT:", rep.product_kind.value, "| origin:", rep.data_origin.value, "| version:", rep.product_version)
    print("ROLES:", rep.roles)
    print("MISSING:", rep.missing)
    print("WARNINGS:", rep.warnings)
    print("DISPLACEMENT SUPPORTED:", rep.displacement_supported, rep.displacement_blockers)
    assert rep.data_origin is not DataOrigin.SYNTHETIC_FIXTURE, "this is a synthetic fixture, not real data"

    verdict = "REAL_DATA_VALIDATION: NOT_PERFORMED"
    if rep.product_kind is ProductKind.GUNW and rep.displacement_supported:
        out = {k: tmp_path / k.value for k in ProductType}
        for d in out.values():
            d.mkdir()
        cfg = ProcessingConfig()
        res = process_gunw(path, rep, cfg, out_dirs=out, tmp_dir=tmp_path / "tmp", min_free_bytes=0)
        now = datetime.now(UTC)
        q = quality_report(rep=rep, cfg=cfg, result=res, status="COMPLETED", started=now, ended=now,
                           input_ref=path.name, errors=[])
        print("DISPLACEMENT STATS:", res.stats["displacement"])
        print("SOFTWARE:", q["software"])
        assert res.stats["displacement"]["valid_pixels"] > 0
        verdict = ("REAL_DATA_PROCESSING: RAN on a real local file (provenance not verified here). "
                   "SCIENTIFIC VALIDATION: NOT_PERFORMED")
        shutil.rmtree(tmp_path / "tmp", ignore_errors=True)
    print(verdict)
