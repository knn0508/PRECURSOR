from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PRECURSOR AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    secret_key: str = "change-me"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://precursor:precursor@localhost:5432/precursor"
    # Comma-separated string (a list-typed field would be JSON-decoded from the env).
    cors_origins: str = "http://localhost:3000"

    # --- Phase 2: data acquisition -------------------------------------------------
    # Earthdata Login. Optional: search/discovery is anonymous; downloads need it.
    earthdata_username: SecretStr | None = None
    earthdata_password: SecretStr | None = None

    data_root: Path = Path("./data")
    aoi_dir: Path | None = None  # defaults to <data_root>/aoi

    # NISAR products searched by default. GOFF and SME2 are optional extras.
    nisar_products: str = "GUNW,GCOV,GSLC"
    # Strict by default: lower-maturity products are an explicit opt-in.
    allowed_maturities: str = "VALIDATED"

    max_concurrent_downloads: int = 2
    request_timeout_s: int = 60
    download_retries: int = 3
    max_file_size_bytes: int = 3 * 1024**3  # a real NISAR GUNW granule is ~1.4 GB
    max_granules_per_request: int = 10
    max_aoi_bbox_degrees: float = 5.0  # guard against "download a whole country"

    enable_nisar: bool = True
    enable_nasadem: bool = True
    enable_gpm: bool = True
    enable_smap: bool = False  # optional provider
    enable_landslide_catalog: bool = True

    # --- Phase 3: InSAR processing -------------------------------------------------
    insar_block_rows: int = 256  # raster rows read per window (bounds memory use)
    insar_timeout_s: int = 3600  # external-tool timeout
    insar_min_free_disk_bytes: int = 1 * 1024**3
    # No universal coherence threshold exists: None = do not mask by coherence.
    insar_coherence_threshold: float | None = None

    gpm_resolution: str = "daily"  # daily | half_hourly | monthly
    smap_collection: str = "SPL3SMP_E"  # 9 km enhanced L3 radiometer soil moisture

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def nisar_product_list(self) -> list[str]:
        return [p.strip().upper() for p in self.nisar_products.split(",") if p.strip()]

    @property
    def allowed_maturity_list(self) -> list[str]:
        return [m.strip().upper() for m in self.allowed_maturities.split(",") if m.strip()]

    @property
    def aoi_directory(self) -> Path:
        return self.aoi_dir or (self.data_root / "aoi")

    @property
    def has_earthdata_credentials(self) -> bool:
        return bool(self.earthdata_username and self.earthdata_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
