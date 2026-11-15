"""Phase 6 read-only endpoints: stored series per area and their descriptive analysis. No forecast route exists."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, ValidationFailed
from app.services.timeseries.analyze import analyze
from app.services.timeseries.store import list_series, read_series
from app.services.timeseries.types import TimeSeriesError

router = APIRouter(prefix="/timeseries", tags=["timeseries"])


@router.get("/areas/{area_id}/series")
def series_list(area_id: uuid.UUID, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {"series": list_series(settings.data_root, area_id)}


@router.get("/areas/{area_id}/series/{zone}/{kind}/analysis")
def series_analysis(area_id: uuid.UUID, zone: str, kind: str, alpha: float = 0.05, gap_factor: float = 2.0, min_period_days: float | None = None,
                    wet_threshold_mm: float = 1.0, api_k: float | None = None, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if not 0 < alpha < 1 or gap_factor <= 0:
        raise ValidationFailed("alpha must be in (0, 1) and gap_factor > 0")
    try:
        s = read_series(settings.data_root, area_id, zone, kind)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except TimeSeriesError as exc:
        raise ValidationFailed(str(exc)) from exc
    return analyze(s, alpha=alpha, gap_factor=gap_factor, min_period_days=min_period_days, wet_threshold_mm=wet_threshold_mm, api_k=api_k)
