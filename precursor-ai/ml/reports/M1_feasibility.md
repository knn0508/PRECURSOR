# M1 data feasibility

Date: 2026-11-15. Evidence: anonymous, read-only catalog queries only (no login, no download). Script: [ml/scripts/m1_catalog_probe.py](../scripts/m1_catalog_probe.py); raw output: [ml/reports/m1_probe/probe_results.json](m1_probe/probe_results.json) (run 2026-11-15 UTC). Collection metadata came through the Phase 2 seam (`cmr.find_collections`, imported read-only; it saw 1 collection for `NISAR_L2_GUNW_V1`); granule counts, first/last dates and sizes came from the public CMR granule search (`CMR-Hits`), because the Phase 2 seam returns lists, not counts. Anything not measured is `NOT_VERIFIED`. Sizes are the catalog `granule_size` of the 20 newest granules (median), not downloads.

**ERRATUM (2026-11-15):** the GLC CSV downloaded in the census ends at 2017-09-28, not 2016-03-07 (see [M1_census_and_download_list](M1_census_and_download_list.md) section 0). Every "GLC ends 2016-03-07" below is superseded; the NISAR non-overlap conclusion stands. Region choice and the final download list are in the census report, which replaces section 6 below.

## 1. NISAR: what the catalog really returns

Collection temporal extent starts 2025-10-01 (BETA) / 2025-10-28 (validated + provisional); open end. Today is 2026-11-15, so the **whole NISAR record is at most ~13.5 months**.

| Collection | Granules (global) | First granule start | Last granule start | Median size (MB) |
|---|---|---|---|---|
| GUNW V1 (validated) | 140 | 2026-09-27 | 2026-10-09 | 2,175 |
| GUNW PROVISIONAL | 94,150 | 2025-10-29 | 2026-10-09 | 2,376 |
| GUNW BETA | 10,217 | 2025-10-17 | 2026-01-08 | 2,285 |
| GCOV V1 | 16,655 | 2026-10-21 | 2026-11-12 | 4,978 |
| GCOV PROVISIONAL / BETA | 163,672 / 23,527 | 2025-10-29 / 2025-10-12 | 2026-10-21 / 2026-01-20 | 586 / 313 |
| GSLC V1 | 17,106 | 2026-10-21 | 2026-11-12 | 13,042 |
| GSLC PROVISIONAL / BETA | 162,907 / 23,450 | 2025-10-29 / 2025-10-12 | 2026-10-21 / 2026-01-20 | 2,729 / 1,504 |
| GOFF V1 | 32 | 2026-10-09 | 2026-10-09 | 1,086 |
| GOFF PROVISIONAL / BETA | 27,717 / 3,666 | 2025-10-29 / 2025-10-17 | 2026-10-09 / 2026-01-08 | 1,082 / 759 |
| SME2 PROVISIONAL / BETA (no validated one) | 103,943 / 13,881 | 2025-10-29 / 2025-10-17 | 2026-10-21 / 2026-01-20 | 77 / 84 |

(Granule start dates are acquisition times. Sizes differ strongly between maturities of the same product; the validated GSLC at ~13 GB is the heaviest.)

**Per candidate region (bbox in JSON), GUNW:**

| Region | GUNW validated | GUNW PROVISIONAL | GUNW BETA | GCOV V1 | GSLC V1 |
|---|---|---|---|---|---|
| Nepal central | 0 | 133 | 20 | 29 | 29 |
| Italy Alps/Apennine | 0 | 224 | 0 | 33 | 33 |
| California central coast | 0 | 353 | 54 | 14 | 17 |
| Oregon/Washington | 0 | 225 | 51 | 19 | 19 |
| Taiwan | 0 | 131 | 43 | 10 | 12 |
| Kyushu (Japan) | 0 | 159 | 0 | 23 | 23 |
| Colombia Andes | 0 | 166 | 27 | 22 | 22 |
| Sabah (Borneo) | 0 | 142 | 0 | 20 | 20 |
| Caucasus (Azerbaijan) | 0 | 106 | 32 | 10 | 11 |
| Puerto Rico | 0 | 73 | 0 | 6 | 6 |

Findings:
- **Validated GUNW exists in none of the 10 regions** (140 granules globally, 12 days of data). Phase 2's default `ALLOWED_MATURITIES=VALIDATED` would return nothing; any NISAR use needs an explicit PROVISIONAL/BETA opt-in, with maturity labelled everywhere.
- Per region the interferogram count is ~70-350 (PROVISIONAL), spanning at most ~11 months. Revisit and baselines: the Phase 2 docs record a 12-day sample baseline; the repeat pattern per region was NOT_VERIFIED (not computed from the counts).
- Temporal depth <= ~13 months means no multi-year InSAR time series, no seasonal-cycle replication, and at most one wet season per region. External evidence in search snippets (Fringe 2026 talk) says 4-5 years are needed; NOT_VERIFIED against the talk text.
- Geographic coverage: all 10 regions are hit; global sampling appears broad. A coverage map was not made.
- NISAR file sizes: ~2.2-2.4 GB per GUNW; 100 GUNW ≈ 230 GB, which is about 4.5x the free disk (see section 5).

## 2. Temporal compatibility of labels (critical)

| Label source | Event dates | Overlap with NISAR (2025-10 -> 2026-11) | Status |
|---|---|---|---|
| NASA Global Landslide Catalog export (data.nasa.gov) | to 2016-03-07 (project docs); series starts 2007 (search snippet) | **None** | dates documented, per-year counts NOT_VERIFIED (the portal API returned 404 for an aggregate query; the CSV was not downloaded) |
| COOLR citizen reports | Mar 2018-Apr 2019 in the 2019 paper (162 events) | None (ends 2019 in that paper) | read; later growth NOT_VERIFIED |
| COOLR "open inventories of rainfall-triggered landslides" (Figshare 10.6084/m9.figshare.26972467, 2025) | 22 inventories, event dates NOT_VERIFIED (file not opened) | Unknown, likely mostly earlier years | NOT_VERIFIED |
| National/regional inventories, USGS landslide inventories, Copernicus EMS, news-derived sets | not queried | not checked | NOT_VERIFIED (no catalog query was made; each needs a manual check) |
| USGS earthquakes (a trigger, not a label) | live | live count: 2,213 events M>=5 globally, 2025-10-01..2026-11-01 (query returned `count: 2213`) | VERIFIED |

**Consequence: no verified landslide label source overlaps the NISAR period.** A NISAR-only model, trained and tested on real labels, cannot be built from what was verified. Labels dated 2025-10 onward would have to come from sources not yet found (news-derived or regional inventories; Copernicus EMS rapid mapping), and even then few and unvetted. The GLC/COOLR events overlap Sentinel-1 only partially: Sentinel-1 begins 2014-10 and GLC ends 2016-03 (~17 months); COOLR citizen reports (2018-2019) and 2018+ inventories overlap fully.

## 3. Alternatives and non-SAR factors (catalog facts)

| Dataset | Source / access | Role | Date range (catalog) | Coverage | Size (measured) | Licence | Maturity / issues |
|---|---|---|---|---|---|---|---|
| OPERA L3 DISP-S1 V1 | ASF/CMR, Earthdata login to download | feature (InSAR displacement) | 2016-07-01 -> 2026-01-29 (granule starts) | **North America only here**: hits in California 6,924, Oregon/WA 3,563, Puerto Rico 1,419, Colombia 297; **0** in Nepal, Italy, Taiwan, Kyushu, Sabah, Caucasus | ~389 MB (sample from Oregon/WA) | NOT_VERIFIED | product validation status NOT_VERIFIED; Phase 3 never read an OPERA file |
| Sentinel-1 SLC | ASF search (asf_search 14.1.0), login to download | raw SAR | 2014-10+ | global; 2023 SLC granules per region: Nepal 467, Italy 843, California 677, Oregon/WA 619, Taiwan 211, Kyushu 153, Colombia 302, Sabah 266, Caucasus 416, Puerto Rico 185 | ~4.6 GB (Nepal sample) | free (Copernicus terms, NOT_VERIFIED here) | **Phase 3 cannot process it** (`BLOCKED_MISSING_INPUT`: needs SNAP/ISCE); processing a regional stack is outside M-stage scope; ~470 x 4.6 GB ≈ 2.2 TB/yr for Nepal |
| Sentinel-1 RTC (OPERA L2 RTC-S1) | CMR | backscatter feature | 2016-04-14 -> 2026-11-14, 77 M granules | global-ish (not checked per region) | NOT_MEASURED | NOT_VERIFIED | |
| ALOS-2 / ALOS PALSAR | JAXA / ASF | L-band history | short name `ALOS_PALSAR_RTC_HIGH_RES` returned 0 hits (wrong name or absent); ALOS-2 not in open CMR as checked | | | | **NOT_VERIFIED**; ALOS-2 commercial/restricted access |
| Copernicus EGMS | egms.land.copernicus.eu (not CMR) | feature (Sentinel-1 PS/DS ground motion), Europe | not queried | Europe only | NOT_MEASURED | CC-BY-like (NOT_VERIFIED) | **NOT_VERIFIED**; no code path in the repo |
| NASADEM_HGT 001 | LPCLOUD, login | static feature | 2000-02-11 (static) | global | 14.3 MB/tile; Nepal bbox needs ~8 tiles ≈ 0.11 GB | NASA open | Phase 2 provider exists; derived products validated only on synthetic data |
| GPM IMERG daily Final V07 | GES_DISC, login | dynamic feature | 1998-01-01 -> **2025-09-30** | global, 0.1 deg | **31.2 MB per day (global file)**; 1 year ≈ 11.4 GB | NASA open | **ends 2025-09-30: no IMERG Final during the whole NISAR period**; latency ~3.5 months; no AOI subsetting in Phase 2 |
| SMAP SPL3SMP_E | NSIDC, login | dynamic feature | 2015-03-31 -> 2026-11-13 | global 9 km | **656 MB per day** (20-granule median) | NASA open | very heavy at multi-year scale; SPL4SMGP (L4, 2015-03-31 -> 2026-11-10) size NOT_MEASURED |
| SoilGrids 2.0 | ISRIC (WebDAV/WCS) | static | model, current | global 250 m | NOT_MEASURED | CC BY 4.0 (snippet) | Phase 4 reader expects an assumed file naming |
| ESA WorldCover 2021 v200 | AWS open bucket, no login | static | 2021 | global 10 m, 3x3 deg COG tiles | ~150 MB/tile (ESTIMATE from Phase 4 docs) | CC BY 4.0 | single-year snapshot |
| Lithology/geology, rivers, faults | not selected | static | | | | | **NOT_VERIFIED**: no source chosen; Phase 4 expects user-placed files |
| USGS earthquakes | FDSN API | trigger feature | live | global | KB | US public domain | catalog queries only; ok |

## 4. Candidate study designs (ranked)

**B. Multi-source susceptibility (Task A) with long-history labels. RECOMMENDED.**
Labels: GLC (+ COOLR/Figshare inventories) over a region chosen **after a label census**; static factors (NASADEM-derived terrain, WorldCover, SoilGrids, lithology if a source is found); long-term rainfall climatology; InSAR only as an optional auxiliary where a real product exists (OPERA DISP in North America). Labels are independent of NISAR, so no temporal conflict.
- Region: not fixed. Candidates for the census: any of the 10 probed regions. Labelled-event counts per region are **NOT_VERIFIED** (the GLC CSV was not downloaded, per the rules); the choice should go to the region with the most dated, accurately located events.
- Expected positives / class balance: unknown (NOT_VERIFIED). Planned background ratio 1:1 to 1:10, reported with sensitivity runs. Success needs on the order of hundreds of positives to support spatial CV; below ~100 a model is not defensible and the track should report that.
- Download: ~0.1 GB (NASADEM, 8 tiles for a Nepal-size bbox) + 0.15-0.3 GB (WorldCover) + a few hundred MB for SoilGrids/others (NOT_MEASURED) + label files. Disk, CPU/GPU (xgboost/LightGBM CUDA already verified in M0), time: hours of compute; days of calendar time dominated by approvals.
- Risks: inventory bias; label positional error; weak signal; no result may be a probability.

**C. Hybrid: B plus a Task B (trigger) model, with OPERA DISP/NISAR as dynamic auxiliary.**
Needs dated events and daily rainfall inside the label period. IMERG Final: 31 MB/day, 2015-2025 ≈ 4,000 days ≈ 125 GB for global files (no subsetting verified), above the ~51 GB free disk (below). Feasible only with a subset service (NOT_VERIFIED) or an external drive, or a short period/region. NISAR cannot supply training history (≤13 months, no labels). Position: do after B shows signal; larger risk and cost.

**A. NISAR-only trigger model. NOT FEASIBLE on verified evidence.**
No label overlap (section 2), ≤13 months history, validated GUNW nonexistent per region, ~230 GB for 100 products. Keep NISAR as a *demonstration of the pipeline on a real recent scene* (inspection via Phase 3, `REAL_DATA_VALIDATION`) rather than as a training source. Not worth proposing a download for model training.

Recommendation: **B**, in two steps, with C only if B justifies it. The user's request to bring data from the NISAR API is feasible technically (catalog works, files are listed) but not scientifically for model training in this period; that is the central finding.

## 5. Resources
- Free disk on the project drive: **51 GB of 953 GB (95% full)**, measured 2026-11-15 (`df`). Any plan above ~30 GB needs external storage or subsetting.
- GPU/compute: see [ML_ENVIRONMENT](../../docs/ml/ML_ENVIRONMENT.md) (xgboost CUDA, LightGBM local CUDA build verified in M0).

## 6. Download proposal (NOTHING DOWNLOADED; approval needed)

Step 1, **label census** (small; decides the region):
| # | File | Source | Auth | Size | Purpose |
|---|---|---|---|---|---|
| 1 | `Global_Landslide_Catalog_Export_rows.csv` | https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv | none | NOT_MEASURED (expected a few MB) | per-region/year event counts, accuracy field, date format check |
| 2 | COOLR rainfall-triggered inventories, Figshare 10.6084/m9.figshare.26972467 | figshare.com | none | NOT_MEASURED (file list not opened) | event dates, positions, overlap with S1 era |

Total: single-digit to low tens of MB (ESTIMATE). Time: minutes. Disk: negligible. Output: per-region dated-event table (counts only, in a report), plus DATASET_LOG rows with SHA-256.

Step 2 (after the census, for the chosen AOI; not yet exact): NASADEM tiles (14.3 MB each; ~8 for a 3.5x2 deg bbox ≈ 0.11 GB), WorldCover tile(s) (~150 MB each, ESTIMATE), SoilGrids layers (NOT_MEASURED), lithology source (undecided). I will return with exact names, counts and total GB once the region is fixed.

NOT proposed: NISAR files for training, Sentinel-1 SLC stacks, multi-year IMERG/SMAP.

## 7. What was not verified
GLC per-year event counts and per-region counts; COOLR/Figshare contents and dates; any regional inventory; OPERA DISP quality and licence; ALOS-2 and EGMS access; actual revisit pattern of NISAR per region; IMERG subsetting options; SMAP L4 size; SoilGrids/lithology sources; NISAR file layout (Phase 3 `REAL_DATA_VALIDATION: NOT_PERFORMED`). Counts above are catalog metadata and may change.

## 8. Risks
Labels are the limiting resource; the NISAR record is shorter than one year; disk is at 95%; ASF/OPERA coverage is North America only; the literature review read 5 of 14 listed papers (see M1_literature).

## 9. Decision needed from you
1. Confirm study design **B** (susceptibility, long-history labels), with C deferred, and NISAR not used for training.
2. Approve the Step 1 label-census downloads (two files, no login).
3. Say whether storage can be extended (external drive) or whether to keep everything under ~30 GB.
4. Candidate regions you care about (any AOI); otherwise the census picks one.
