# M1 label census, region selection and download proposal

Date: 2026-11-15. Scripts: [m1_census.py](../scripts/m1_census.py), [m1_candidate_coverage.py](../scripts/m1_candidate_coverage.py). Raw outputs: `m1_probe/census_results.json`, `m1_probe/candidate_coverage.json`. This stage downloaded only the two approved label files (see section 1). No login, nothing else downloaded. M2 is not started.

## 0. Correction to earlier M1 text
The GLC export in hand contains events up to **2017-09-28** (last row), not 2016-03-07 as stated in `docs/nasa-data-sources.md`, `docs/phase-2-data-acquisition.md` and in my earlier M1 reports (page metadata modified 2025-05-29; row `last_edited_date` 2018-02-15). The Phase 2 docs were NOT edited (outside the track); the discrepancy is reported here for you to decide. The conclusion "GLC does not overlap NISAR (2025-10 onward)" is unchanged. Day/month order of `event_date` parsed as MM/DD with no failures (0 unparseable of 11,033), which supports the Phase 2 assumption but is not a proof.

## 1. Files downloaded (approved)
| File | URL | Licence | Retrieved (UTC) | Bytes | SHA-256 |
|---|---|---|---|---|---|
| `data/ml/raw/census/glc.csv` | https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv | "License not specified" (CKAN metadata) | 2026-11-14 | 8,479,717 (measured by a 1-byte ranged GET: `Content-Range: bytes 0-0/8479717`) | `2c4898899dd4f373c4320e121c5b655ebb5394d431fa42e57ec4828d07d48b04` |
| `data/ml/raw/census/nasa_coolr_new_events.zip` | https://ndownloader.figshare.com/files/54363830 (DOI 10.6084/m9.figshare.26972467.v1) | CC BY 4.0 | 2026-11-14 | 1,609,694 | `2a019c6a955a4e9ae8da9b8740c1f64c3cd9a162e90972bb03509a5f119dfd38` |
Total 10.09 MB (limit 100 MB). The zip was extracted to `data/ml/interim/census/` (Esri file geodatabase, one layer `nasa_coolr_events_new_point`, 15,274 points).

## 2. What the files contain (measured)
- **GLC**: 11,033 rows, all dated and with valid coordinates; 1988-11-07 to 2017-09-28; ~97% of rows from 2007 on. `location_accuracy`: 5km 3,178; 1km 2,185; 25km 1,470; 10km 1,435; exact 1,386; 50km 794; unknown 542; 100km 25; 250km 16. Trigger: downpour 4,680, rain 2,592, unknown 1,691, continuous_rain 748, tropical_cyclone 561 (others small).
- **COOLR new events**: 15,274 points, dated 2019-04-23 to 2023-08-06 (57 in 2019, 5,163 in 2022, 10,054 in 2023). All four `ls_trig` values are rain-type (Rain, Downpour, Cyclone, Heavy Rain). **No location-accuracy field.** Positions come from PlanetScope-based mapping (3,862 automatic "SALaD-CD" in Mexico; the rest manual, each inventory covering one storm). Positional error and the mapped footprint (where absence is informative) are **not in the file** (NOT_VERIFIED).

## 3. Census definitions
Usable = valid coordinates AND dated AND rainfall-triggered (rain, downpour, continuous_rain, tropical_cyclone, monsoon) AND landslide-type (snow_avalanche, lahar, riverbank_collapse, unknown excluded) AND inside the **ML-usable period 2014-10-03 .. 2025-09-30** (Sentinel-1 start to IMERG Final end, from the catalog queries). GLC "accurate" = `exact`/`1km`/`5km` (strict) or plus `10km` (relaxed); COOLR new = all counted (no field). Windows: 3x3 degree, 1-degree stride, top non-overlapping; nothing hard-coded.

Funnel (rows -> usable in period, strict): GLC 11,033 -> rain 8,710 -> type 8,665 -> all-years strict 4,918 -> **in period strict 1,812** (relaxed 2,142). COOLR new 15,274 -> **15,274** (all pass; they are, by construction, rain-triggered and in period).

## 4. Top 3 candidates by raw usable count, and the top 3 multi-date alternatives
| Rank | Window (W,S,E,N) | Strict usable events (in period) | Relaxed | Distinct event dates | Share on one date | Distinct 30 m cells | Sources | Years |
|---|---|---|---|---|---|---|---|---|
| 1 | Oaxaca, Mexico (-97,15,-94,18) | **3,862** | 3,864 | **1** (2022-05-30, Hurricane Agatha) | 100% | 3,841 | COOLR 3,862 | 2022 |
| 2 | N. Luzon, Philippines (119,16,122,19) | **3,199** | 3,211 | 14 | 99.5% (2023-07-26) | 3,170 (COOLR) | COOLR 3,183; GLC 16 | 2015-17 (GLC 16), 2023 |
| 3 | N. Vietnam (102,21,105,24) | **1,951** | 1,952 | 2 | 99.9% | not computed | COOLR 1,950; GLC 1 | 2015, 2023 |
| alt 1 | Oregon/Washington (-124,45,-121,48) | **111** (327 in all years from 2007) | 124 | **62** | 8% | n/c | GLC 111 | 2014-2017 (65 in 2017) |
| alt 2 | N. California (-123,37,-120,40) | **115** (173 all years) | 121 | **58** | 10% | n/c | GLC 115 | 2014-2017 (85 in 2017) |
| alt 3 | S. California (-119,32,-116,35) | **78** (167 all years) | 81 | **37** | 10% | n/c | GLC 78 | 2014-2017 |
Reference (not a candidate): Nepal window (83,27,86,30) has only 105 strict all-years and 37 in-period GLC events.

**Expected positives:** at most the event counts above (distinct 30 m cells shown where computed). For GLC windows the real number of usable positive *cells* is smaller and the cell scale must be coarse, because strict accuracy is up to 5 km (Phase 5 buffer rule would exclude background within ~10 km of each event). Positive-cell counts per candidate cell size are computed in M3 (NOT_VERIFIED here).

Catalog coverage of the same windows (anonymous queries, 2026-11-15; Sentinel-1 SLC granules per year 2015/2017/2022/2023): Oaxaca 108/432/374/369; Luzon 182/264/165/180; Vietnam 263/502/429/436; OR-WA 239/442/386/470; CA-N 247/614/556/558; CA-S 281/517/403/421. OPERA DISP-S1 granules: Oaxaca 5,580; OR-WA 3,115; CA-N 5,980; CA-S 6,221; **Luzon 0; Vietnam 0**. NISAR GUNW PROVISIONAL (not for training): 124-357 per window.

## 5. Selection and reasoning
The three highest counts are single-storm COOLR inventories. They are large but weak for this study:
- one (or nearly one) event date, so a temporal hold-out is impossible and the Task B trigger model is impossible; spatial autocorrelation within one storm footprint is extreme;
- the file has **points only, no footprint or accuracy**, so I cannot say where absence of a point is informative; background cells drawn from the area would include unmapped slides (false background);
- no OPERA coverage for Luzon or Vietnam; no lithology source verified for them.

The GLC windows have fewer positives (hundreds, not thousands) but 37-62 distinct dates each (temporal hold-out feasible), documented accuracy classes, full catalog coverage (NASADEM 9/9 tiles, Sentinel-1, OPERA DISP, IMERG, WorldCover) and a verified-existing lithology product (USGS SGMC, US only). Their weaknesses: news-derived and biased to reported, accessible places (US reporting), positional error up to 5 km, temporal clustering (about 74% of CA-N events in 2017 and 59% of OR-WA, mostly the winter 2017 storms), and counts that are borderline for spatial CV.

**Selection (my proposal, you decide):**
- **Primary B1 = three US West Coast windows** (OR-WA, N. California, S. California; GLC labels; 304 strict in-period events, 667 in all years from 2007, usable for the static susceptibility task).
- **Optional B2 = N. Luzon 2023 (COOLR)** as a separate, clearly labelled event-inventory study (3,183 events, one storm): only if you want a large-positive test; carries the footprint/background problem and has no verified lithology source (NOT_VERIFIED; a global lithology map would need a separate check).
- Mexico and Vietnam are dropped (same single-storm problem; Mexico is 100% automatic mapping).

## 6. Exact download list proposed for approval (M2 would run it; nothing is downloaded now)
All sizes from catalog metadata (`granule_size` or HTTP HEAD on public files), measured 2026-11-15, except where marked.

| # | Dataset | Items | Source / access | Login | Size |
|---|---|---|---|---|---|
| 1 | NASADEM_HGT 001 tiles, B1 | 27 tiles: OR-WA n45-n47 x w124-w122 (9, 109.8 MB); N. CA n37-n39 x w123-w121 (9, 94.5 MB); S. CA n32-n34 x w119-w117 (9, 72.6 MB) | LPCLOUD via Phase 2 `NASADEMDataProvider` | Earthdata | **276.9 MB** |
| 2 | ESA WorldCover 2021 v200 tiles, B1 | 8 tiles: N45W126 (18.5), N45W123 (65.0), N36W123 (87.6), N39W123 (69.7), N30W120 (4.8), N30W117 (60.2), N33W120 (101.2), N33W117 (90.2) MB | public AWS bucket `esa-worldcover` (eu-central-1) | none | **497.2 MB** |
| 3 | GPM IMERG Monthly Final V07 (`GPM_3IMERGM`) | 132 monthly global files, 2014-10 .. 2025-09; for rainfall climatology and wet-season totals only | GES_DISC | Earthdata | **~2.36 GB** (ESTIMATE: 132 x 17.9 MB median of 20 sampled files) |
| 4 | USGS SGMC geodatabase (lithology, US only) | 1 file `USGS_SGMC_Geodatabase.zip` (DOI 10.5066/F7WH2N65, ScienceBase item 5888bf4fe4b05ccb964bab9d); HEAD and the ScienceBase API returned 403 | ScienceBase | none (expected) | **NOT_MEASURED** (the 2 GB per-file cap is checked before download; if it exceeds 2 GB I stop and ask) |
| 5 | Labels | already local (section 1) | | | 10.1 MB (done) |
| | **B1 total (excluding item 4)** | 35 files + 132 files | | | **~3.1 GB** (limit 30 GB) |

Optional B2 (N. Luzon): NASADEM 7 tiles (59.4 MB; 2 of the 9 are ocean-only and absent from the catalog) + WorldCover N15E117 (4.4), N15E120 (55.5), N18E120 (9.5) = 69.4 MB; no lithology source. B2 total ≈ 0.13 GB.

Limits check: total about 3.1 GB (+ SGMC unmeasured, + B2 0.13 GB) is far below 30 GB; the largest known file is ~101 MB (< 2 GB); disk free was 51 GB (measured 2026-11-15) so at least 15 GB would remain. After downloads I will re-measure free disk.

**Not proposed:** NISAR files (not used for training); Sentinel-1 SLC (4.6 GB each, Phase 3 cannot process, ~470 per year per window); OPERA DISP-S1 (389 MB each; possible later auxiliary only for B1, decide after B shows signal); daily IMERG (31 MB/day; design C only); SMAP (656 MB/day); SoilGrids (size not measurable; later optional).

## 7. Not verified / risks
- SGMC size, licence text and file layout; whether WorldCover tile names above match the real bucket for the non-measured ones (all eight were HEAD-checked with HTTP 200, so the names are right; contents unread).
- IMERG monthly total is an estimate from 20 files.
- COOLR positional accuracy and footprint; label precision for all GLC rows; GLC row-level duplicates between GLC and COOLR (not checked).
- Census counts depend on my definitions (rain-type triggers, strict accuracy, period); different choices change numbers.
- Lithology for non-US regions is unresolved (blocks B2 as a full design).

## 8. Decision needed from you
1. Approve region(s): **B1 (US West Coast, 3 windows)**; B2 (Luzon) yes/no.
2. Approve the download list in section 6 (items 1-4; login needed for items 1 and 3, using the Phase 2 pipeline), and the rule that item 4 is size-checked first.
3. (Resolved 2026-11-15: user approved a docs-only correction; see TASK_LOG.)
