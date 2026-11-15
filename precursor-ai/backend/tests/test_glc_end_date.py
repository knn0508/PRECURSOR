"""Regression: the Global Landslide Catalog limitation texts state the real last-event date (2017-09-28, measured on the
downloaded CSV in the ML M1 census: ml/reports/M1_census_and_download_list.md), not the earlier wrong 2016-03-07."""
from app.api.v1.environmental import HIST_LIMITS
from app.services.data_acquisition.providers import landslide_catalog as lc
from app.services.environmental.features.historical_event_features import LIMITATION
from app.services.features_cv.dataset import CAVEATS

OLD, NEW = "2016-03-07", "2017-09-28"


def test_limitation_texts_state_corrected_end_date():
    for text in (lc.LIMITATIONS, LIMITATION, HIST_LIMITS[0], CAVEATS[0]):
        assert NEW in text and OLD not in text
    assert lc.EXPORT_DATE == NEW


def test_legacy_version_identifier_unchanged():
    assert lc.DEFAULT_VERSION == "export-2016-03-07"  # stored in DB default/migration/file names; not a date claim
