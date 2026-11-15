// Mirrors backend/app/schemas/data_acquisition.py. Keep in sync. UUIDs and datetimes are strings.

export type Maturity = "VALIDATED" | "PROVISIONAL" | "BETA";
export type AcquisitionStatus =
  | "DISCOVERED" | "QUEUED" | "DOWNLOADING" | "DOWNLOADED" | "VALIDATING"
  | "VALIDATED" | "FAILED" | "SKIPPED" | "UNAVAILABLE";
export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
export type ProviderName = "NISAR" | "NASADEM" | "GPM" | "SMAP" | "OPERA" | "LANDSLIDE_CATALOG";
export type DataKind = "metadata_only" | "downloaded" | "validated";
type Json = Record<string, unknown>;

export interface CollectionRead {
  id: string;
  provider: ProviderName;
  collection_short_name: string;
  dataset_name: string;
  product_type: string;
  version: string;
  maturity: Maturity | null;
  description: string | null;
  documentation_url: string | null;
  cmr_concept_id: string | null;
  discovered_at: string;
}

/** Exactly one of monitored_area_id / geometry. */
export interface AOIInput {
  monitored_area_id?: string | null;
  geometry?: Json | null;
  name?: string | null;
}

export interface SearchRequest {
  aoi: AOIInput;
  start_date?: string | null;
  end_date?: string | null;
  providers?: ("NISAR" | "OPERA" | "NASADEM" | "GPM")[];
  products?: string[];
  maturities?: Maturity[];
  max_results?: number;
  dry_run?: boolean;
}

export interface GranuleResult {
  provider: ProviderName;
  granule_id: string;
  collection_short_name: string;
  product_type: string;
  version: string;
  maturity: Maturity | null;
  acquisition_start: string | null;
  acquisition_end: string | null;
  temporal_baseline_days: number | null;
  orbit_direction: string | null;
  relative_orbit: number | null;
  file_format: string | null;
  file_size_bytes: number | null;
  footprint: Json | null;
  registered: boolean;
  acquisition_id: string | null;
  status: AcquisitionStatus;
  data_kind: DataKind;
}

export interface SearchResponse {
  dry_run: boolean;
  aoi_name: string;
  results: GranuleResult[];
  warnings: string[];
  provider_errors: Record<string, string>;
}

export interface AcquisitionRead {
  id: string;
  monitored_area_id: string | null;
  collection_id: string;
  provider: ProviderName;
  granule_id: string;
  product_type: string;
  acquisition_start: string | null;
  acquisition_end: string | null;
  processing_date: string | null;
  orbit_direction: string | null;
  relative_orbit: number | null;
  footprint: Json | null;
  crs: string;
  file_format: string | null;
  file_size_bytes: number | null;
  download_url: string | null;
  local_file_path: string | null;
  checksum: string | null;
  checksum_algorithm: string | null;
  maturity: Maturity | null;
  status: AcquisitionStatus;
  retrieved_at: string | null;
  metadata_json: Json;
  validation_report: Json;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface AcquisitionList {
  items: AcquisitionRead[];
  total: number;
}

export interface DownloadCreate {
  acquisition_ids: string[];
}

export interface DownloadJobRead {
  id: string;
  acquisition_id: string;
  status: JobStatus;
  progress: number;
  bytes_downloaded: number;
  attempts: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  granule_id: string | null;
  product_type: string | null;
}

export interface DownloadJobList {
  items: DownloadJobRead[];
  total: number;
}

/** POST /data/downloads (202). `skipped` maps acquisition_id to the reason it was not queued. */
export interface DownloadCreateResponse {
  jobs: DownloadJobRead[];
  skipped: Record<string, string>;
}

export interface EnvironmentalAcquireRequest {
  aoi: AOIInput;
  start_date: string;
  end_date: string;
  include_smap?: boolean;
  dry_run?: boolean;
  max_granules?: number;
}

export interface EnvironmentalAcquireResponse {
  dry_run: boolean;
  results: GranuleResult[];
  jobs: DownloadJobRead[];
  provider_errors: Record<string, string>;
  warnings: string[];
}

export interface LandslideEventRead {
  id: string;
  external_event_id: string;
  event_date: string | null;
  location_name: string | null;
  country: string | null;
  trigger: string | null;
  landslide_type: string | null;
  source: string | null;
  longitude: number;
  latitude: number;
  original_attributes: Json;
  dataset_version: string;
}

export interface LandslideEventList {
  items: LandslideEventRead[];
  total: number;
  limitations: string;
}

export interface LandslideImportRequest {
  file_path?: string | null;
  force?: boolean;
}

export interface LandslideImportResponse {
  dataset_version: string;
  inserted: number;
  updated: number;
  skipped_invalid: number;
  source_file: string;
  limitations: string;
}

export interface ProviderStatus {
  name: ProviderName;
  enabled: boolean;
  optional: boolean;
  authentication: "not_required" | "configured" | "missing" | "failed";
  collections_discovered: number;
  last_successful_acquisition: string | null;
  note: string | null;
}

export interface DataStatus {
  providers: ProviderStatus[];
  earthdata_credentials_configured: boolean;
  acquisitions_registered: number;
  files_downloaded: number;
  files_validated: number;
  jobs_failed: number;
  jobs_active: number;
  landslide_events: number;
  product_distribution: Record<string, number>;
  storage_free_bytes: number | null;
  storage_used_bytes: number | null;
  data_root: string;
}
