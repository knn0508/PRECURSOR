# Data storage

Root: `DATA_ROOT` (default `./data`; `/data` in Docker, where `./data` is bind-mounted). `storage.ensure_layout()` creates the tree.

```
data/
  raw/
    nisar/{gunw,gcov,gslc,goff,sme2}/
    nasadem/
    gpm/imerg/
    smap/
    landslide_catalog/        CSV + .sha256 sidecar
  metadata/
    collections/              <collection_short_name>.json
    acquisitions/             <granule_id>.json   (provenance manifests)
    manifests/                reserved
  processed/                  reserved for later phases
  samples/
  aoi/                        your AOI files
```

## Phase 4 environmental outputs

`data/processed/environmental/<area_id>/{dem,rainfall,soil,land_cover,historical_landslides,seismic,insar,aligned,features,reports,intermediate}/` (elevation.tif, slope.tif, aspect.tif, quality_report_<run>.json). Source files (`data/raw`, `data/external/<provider>/`) are only read; soil and land-cover GeoTIFFs are placed in `data/external/soilgrids/` and `data/external/land_cover/` by the user after approving a download. See [phases/PHASE_04.md](phases/PHASE_04.md).

## Phase 3 processed outputs

`data/processed/insar/{displacement,coherence,velocity}/<run_id>/*.tif` (COG), `quality_reports/`, `inspections/`, `metadata/` per run, `intermediate/` (cleaned after success), and `data/samples/insar/` for labelled synthetic or explicitly placed local inputs. Raw files are only read. See [scientific/INSAR_METHODOLOGY.md](scientific/INSAR_METHODOLOGY.md).

## File naming

- `storage.target_path()` builds `<YYYYMMDD>__<filename>` (acquisition start date, or `undated`), sanitised to `[A-Za-z0-9._-]`.
- **As implemented today**, the orchestrator passes the provider directory as `dest_dir` to the providers, which then save the file under its original (sanitised) filename in that directory, without the date prefix. The prefixed name is used only when `dest_dir` is omitted. Do not rely on the prefix.
- Landslide CSV: `global_landslide_catalog_export-2016-03-07__retrieved_<YYYYMMDD>.csv`.

## Download behaviour

| Rule | Detail |
|---|---|
| Temp file | Bytes go to `<name>.part`; on success `os.replace` makes it final (atomic). |
| Resume | An existing `.part` is continued with an HTTP `Range` request; an inconsistent `Content-Range` restarts the file. |
| Retries | `DOWNLOAD_RETRIES` retries with exponential backoff + jitter for timeouts, connection errors, 429/5xx, truncated streams. 401/403 -> auth error; 404/410 and size/checksum policy errors are not retried. |
| No silent overwrite | If the destination exists, it is accepted only if it matches the published checksum (or the expected size); otherwise the download is refused. |
| Size cap | Refused if the catalog size, `Content-Length`, or the received bytes exceed `MAX_FILE_SIZE_BYTES`. Needs free disk of 1.05 x expected size. |
| Checksums | SHA-256 is computed locally and stored in `data_acquisitions.checksum`. The provider's published checksum (NISAR: MD5) is kept in `metadata_json['published_checksum']` and verified when present. |

## Manifests

After a successful validation, `data/metadata/acquisitions/<granule_id>.json` and `data/metadata/collections/<short_name>.json` are written: provider, granule id, collection/version, product type, maturity, status, dates, file format/size, source URL **without query string**, local path, checksum, retrieval time, validation report, and the note "File checks only; not a scientific validation." No credentials. Manifest writing is best effort: a failure is logged and does not fail the job.

## Docker and git

- `docker-compose.yml` mounts `./data:/data` and sets `DATA_ROOT=/data`.
- `.gitignore` ignores `data/raw/**` and `data/metadata/**` (except `.gitkeep`) and `data/processed/*`.

## Storage estimates

| Item | Size |
|---|---|
| One NISAR GUNW granule | about 1.4-2 GB |
| 5 GUNW granules | about 7-10 GB |
| NASADEM tile (zip) | about 14 MB |
| IMERG daily global file | **not measured** |

Per-file cap default is 3 GiB. Check free space before a bulk request; `status` reports free/used bytes.
