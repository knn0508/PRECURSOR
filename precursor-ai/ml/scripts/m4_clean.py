"""M4 cleaning: one command, deterministic (fixed seed), reversible (flags only), no downloads, no modelling.

    ml/.venv/Scripts/python ml/scripts/m4_clean.py
Reads data/ml/interim/m3 (5 km) and m3_10km, writes data/ml/processed/m4/{5km,10km}/ and data/ml/processed/m4/ndvi_georef_qc.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3, m4  # noqa: E402

SOIL_UNITS_EVIDENCE = {
    "source": "ISRIC SoilGrids FAQ, 'SoilGrids layers' page (last updated 2026-09-02): https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html",
    "rule_quoted": "By dividing the predictions values by the values in the Conversion factor column, the user can obtain the more familiar units in the Conventional units column.",
    "table": {"clay": {"mapped": "g/kg", "factor": 10, "conventional": "g/100g (%)"}, "sand": {"mapped": "g/kg", "factor": 10, "conventional": "g/100g (%)"},
              "silt": {"mapped": "g/kg", "factor": 10, "conventional": "g/100g (%)"}, "cfvo": {"mapped": "cm3/dm3 (vol permille)", "factor": 10, "conventional": "cm3/100cm3 (vol%)"},
              "bdod": {"mapped": "cg/cm3", "factor": 100, "conventional": "kg/dm3"}},
    "applied_in_m3b": {"clay": 10, "sand": 10, "silt": 10, "cfvo": 10},
    "match": True,
    "not_stated_on_page": "Int16 storage and nodata value (the tile VRT itself declares Int16 and nodata -32768, read in M2b)",
    "status": "VERIFIED against the official page (read by a fetch agent on 2026-11-15); the page does not describe the tile data type",
}


def main():
    cfg = m4.load_config()
    out = m4.PROCESSED / "m4"
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads((m3.RAW / "manifest_round2.json").read_text())
    q = m4.ndvi_georef_qc(man)
    q.to_csv(out / "ndvi_georef_qc.csv", index=False)
    if len(q) == 0:
        print("STOP: no NDVI granules were checked")
        return 2
    bad = q[~q.ok]
    print("NDVI georeferencing QC:", len(q), "granules,", len(bad), "disagree", bad.file.tolist()[:5])
    (out / "soilgrids_units_check.json").write_text(json.dumps(SOIL_UNITS_EVIDENCE, indent=1))
    if len(bad):
        print("STOP: NDVI granules disagree with the tile arithmetic; they must be excluded from the NDVI statistics before the cleaned dataset is built")
        return 2
    summary = {}
    for name, cell, d in (("5km", 5000, m3.INTERIM), ("10km", 10000, m3.INTERIM.parent / "m3_10km")):
        summary[name] = m4.run_grid(d, out / name, cell, cfg)
        print(name, {k: summary[name][k] for k in ("events_clean_strict_all_years", "cells_excluded", "background_selected", "leakage_audit")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
