"""M1 label census over the two approved label files (local, already downloaded; no network).

Inputs  : data/ml/raw/census/glc.csv ; data/ml/interim/census/nasa_coolr_new_events/*.gdb (unzipped COOLR zip)
Output  : ml/reports/m1_probe/census_results.json
Usable  : dated + located + rainfall-triggered + landslide-type, inside the ML-usable period
          (Sentinel-1 start 2014-10-03 .. IMERG Final end 2025-09-30, both from catalog queries).
Located : GLC location_accuracy in STRICT {exact,1km,5km} or RELAXED {+10km}; COOLR new events have NO accuracy field
          (positions come from PlanetScope mapping; their positional error is NOT_VERIFIED) and are reported separately.
Windows : 3x3 degree windows on a 1-degree stride, ranked by STRICT usable count; top 3 non-overlapping. No region is hardcoded.
Run     : ml/.venv/Scripts/python ml/scripts/m1_census.py   (from precursor-ai/)
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GLC = ROOT / "data/ml/raw/census/glc.csv"
GDB = ROOT / "data/ml/interim/census/nasa_coolr_new_events/nasa_coolr_new_events.gdb"
OUT = ROOT / "ml/reports/m1_probe/census_results.json"

USE_START, USE_END = pd.Timestamp("2014-10-03"), pd.Timestamp("2025-09-30")
RAIN = {"rain", "downpour", "continuous_rain", "tropical_cyclone", "monsoon"}
BAD_CAT = {"snow_avalanche", "lahar", "riverbank_collapse", "unknown"}
STRICT, RELAXED = {"exact", "1km", "5km"}, {"exact", "1km", "5km", "10km"}
CELL = 0.00027  # ~30 m in degrees at the equator; used only to de-duplicate positives
WIN, STRIDE = 3.0, 1.0


def load() -> pd.DataFrame:
    g = pd.read_csv(GLC)
    g["date"] = pd.to_datetime(g.event_date, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    glc = pd.DataFrame({
        "src": "GLC", "id": g.event_id.astype(str), "date": g.date, "lon": g.longitude, "lat": g.latitude,
        "acc": g.location_accuracy.fillna("unknown"), "trig": g.landslide_trigger.fillna("unknown"),
        "cat": g.landslide_category.fillna("unknown"), "country": g.country_name,
    })
    x = gpd.read_file(GDB, layer="nasa_coolr_events_new_point")
    coolr = pd.DataFrame({
        "src": "COOLR_NEW", "id": x.ev_id.astype(str), "date": pd.to_datetime(x.ev_date).dt.tz_localize(None),
        "lon": x.longitude, "lat": x.latitude, "acc": "no_field", "trig": "rain",  # all four ls_trig values are rain-type
        "cat": x.ls_cat.str.lower(), "country": x.ctry_name,
    })
    return pd.concat([glc, coolr], ignore_index=True)


def flags(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["coords_ok"] = d.lat.between(-90, 90) & d.lon.between(-180, 180) & ~((d.lat == 0) & (d.lon == 0))
    d["dated"] = d.date.notna()
    d["rain"] = d.trig.isin(RAIN)
    d["type_ok"] = ~d.cat.isin(BAD_CAT)
    d["in_period"] = d.date.between(USE_START, USE_END)
    base = d.coords_ok & d.dated & d.rain & d.type_ok
    glc = d.src == "GLC"
    d["usable_all_years_strict"] = base & ((glc & d.acc.isin(STRICT)) | ~glc)
    d["strict"] = base & d.in_period & ((glc & d.acc.isin(STRICT)) | ~glc)
    d["relaxed"] = base & d.in_period & ((glc & d.acc.isin(RELAXED)) | ~glc)
    d["cell"] = list(zip(np.floor(d.lon / CELL).astype(int), np.floor(d.lat / CELL).astype(int)))
    return d


def windows(d: pd.DataFrame, col: str):
    u = d[d[col]]
    res = []
    for w in np.arange(-180, 180 - WIN + 1e-9, STRIDE):
        for s in np.arange(-60, 70 - WIN + 1e-9, STRIDE):
            m = u[(u.lon >= w) & (u.lon < w + WIN) & (u.lat >= s) & (u.lat < s + WIN)]
            if len(m):
                res.append((len(m), float(w), float(s)))
    res.sort(reverse=True)
    picked: list = []
    for n, w, s in res:
        if all(abs(w - pw) >= WIN or abs(s - ps) >= WIN for _, pw, ps in picked):
            picked.append((n, w, s))
        if len(picked) == 3:
            break
    return picked


def describe(d: pd.DataFrame, w: float, s: float) -> dict:
    m = d[(d.lon >= w) & (d.lon < w + WIN) & (d.lat >= s) & (d.lat < s + WIN)]
    st = m[m.strict]
    return {
        "bbox_wsen": [w, s, w + WIN, s + WIN],
        "total_records": int(len(m)),
        "strict_usable_events": int(len(st)),
        "relaxed_usable_events": int(m.relaxed.sum()),
        "strict_distinct_30m_cells_(expected_positive_cells_upper_bound)": int(st.cell.nunique()),
        "by_source_strict": st.src.value_counts().to_dict(),
        "per_year_strict": {int(k): int(v) for k, v in st.date.dt.year.value_counts().sort_index().items()},
        "countries_strict": st.country.value_counts().head(5).to_dict(),
        "glc_accuracy_mix_all_usable_base": m[m.src == "GLC"].acc.value_counts().to_dict(),
        "all_years_strict_(2007+)": int(m.usable_all_years_strict.sum()),
        "distinct_event_dates_strict": int(st.date.dt.normalize().nunique()),
        "top_event_dates_strict": {str(k.date()): int(v) for k, v in st.date.dt.normalize().value_counts().head(3).items()},
        "max_share_on_one_date": round(float(st.date.dt.normalize().value_counts().iloc[0] / len(st)), 3) if len(st) else None,
    }


def main() -> None:
    d = flags(load())
    out = {
        "inputs": {"glc_rows": int((d.src == "GLC").sum()), "coolr_new_rows": int((d.src == "COOLR_NEW").sum())},
        "date_range": {s: [str(d[(d.src == s) & d.dated].date.min()), str(d[(d.src == s) & d.dated].date.max())]
                       for s in ("GLC", "COOLR_NEW")},
        "usable_period": [str(USE_START.date()), str(USE_END.date())],
        "funnel": {},
    }
    for s in ("GLC", "COOLR_NEW"):
        e = d[d.src == s]
        out["funnel"][s] = {
            "rows": len(e), "coords_ok": int(e.coords_ok.sum()), "dated": int(e.dated.sum()),
            "rain_triggered": int((e.coords_ok & e.dated & e.rain).sum()),
            "plus_landslide_type": int((e.coords_ok & e.dated & e.rain & e.type_ok).sum()),
            "all_years_strict": int(e.usable_all_years_strict.sum()),
            "in_period_strict": int(e.strict.sum()), "in_period_relaxed": int(e.relaxed.sum()),
        }
    out["glc_accuracy_counts_in_period_rain"] = d[(d.src == "GLC") & d.in_period & d.rain].acc.value_counts().to_dict()
    out["per_year_strict_global"] = {s: {int(k): int(v) for k, v in
                                         d[(d.src == s) & d.strict].date.dt.year.value_counts().sort_index().items()}
                                     for s in ("GLC", "COOLR_NEW")}
    out["top_windows_strict"] = [describe(d, w, s) for _, w, s in windows(d, "strict")]
    # Same ranking using GLC only (more independent of the 2022-23 PlanetScope inventories)
    g = d.copy()
    g["glc_only"] = g.strict & (g.src == "GLC")
    out["top_windows_glc_only"] = [describe(d, w, s) for _, w, s in windows(g, "glc_only")]
    g["glc_all_years"] = g.usable_all_years_strict & (g.src == "GLC")
    out["top_windows_glc_all_years_static_use"] = [describe(d, w, s) for _, w, s in windows(g, "glc_all_years")]
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("inputs", "date_range", "funnel")}, indent=1, default=str))
    for key in ("top_windows_strict", "top_windows_glc_only", "top_windows_glc_all_years_static_use"):
        print(key)
        for w in out[key]:
            print(" ", w["bbox_wsen"], w["strict_usable_events"], w["relaxed_usable_events"],
                  w["by_source_strict"], w["countries_strict"], w["per_year_strict"],
                  "dates", w["distinct_event_dates_strict"], "maxshare", w["max_share_on_one_date"], "allyrs", w["all_years_strict_(2007+)"])


if __name__ == "__main__":
    main()
