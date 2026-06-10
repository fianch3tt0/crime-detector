"""Phase 1 tests: ArcGISClient paging + incremental pull, normalize()."""
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import responses as responses_lib

from crime_detector.ingestion.client import ArcGISClient
from crime_detector.ingestion.normalizer import NormalizedRecord, normalize
from tests.conftest import ARCGIS_URL, MALFORMED_FEATURES, SAMPLE_FEATURES, _make_feature, _make_page


# ---------------------------------------------------------------------------
# ArcGISClient tests
# ---------------------------------------------------------------------------

def _register_page(rsps, features, exceeded=False, status=200):
    rsps.add(
        responses_lib.GET,
        ARCGIS_URL,
        json=_make_page(features, exceeded=exceeded),
        status=status,
    )


def _make_client(page_size=1000):
    return ArcGISClient(endpoint=ARCGIS_URL, page_size=page_size)


class TestArcGISClientPaging:
    def test_fetch_single_page(self, mock_arcgis):
        _register_page(mock_arcgis, SAMPLE_FEATURES)  # no exceededTransferLimit → stop
        client = _make_client()
        results = list(client.fetch_all())
        assert len(results) == 5

    def test_fetch_multi_page(self, mock_arcgis):
        page_size = 3
        page1 = SAMPLE_FEATURES[:3]
        page2 = SAMPLE_FEATURES[3:5]
        _register_page(mock_arcgis, page1, exceeded=True)   # more data → continue
        _register_page(mock_arcgis, page2, exceeded=False)  # last page → stop
        client = _make_client(page_size=page_size)
        results = list(client.fetch_all())
        assert len(results) == 5

    def test_paging_stops_when_exceeded_transfer_limit_false(self, mock_arcgis):
        _register_page(mock_arcgis, SAMPLE_FEATURES[:3], exceeded=True)
        _register_page(mock_arcgis, [], exceeded=False)
        client = _make_client(page_size=3)
        results = list(client.fetch_all())
        assert len(results) == 3

    def test_incremental_date_filter_sends_timestamp_where(self, mock_arcgis):
        _register_page(mock_arcgis, [])
        since = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        client = _make_client()
        list(client.fetch_all(since=since))

        assert len(mock_arcgis.calls) == 1
        req_url = mock_arcgis.calls[0].request.url
        qs = parse_qs(urlparse(req_url).query)
        assert "where" in qs
        assert "TIMESTAMP" in qs["where"][0]
        assert "2024-01-15" in qs["where"][0]

    def test_no_date_filter_without_since(self, mock_arcgis):
        _register_page(mock_arcgis, [])
        client = _make_client()
        list(client.fetch_all(since=None))

        req_url = mock_arcgis.calls[0].request.url
        qs = parse_qs(urlparse(req_url).query)
        assert qs.get("where") == ["1=1"]

    def test_outsr_4326_always_sent(self, mock_arcgis):
        _register_page(mock_arcgis, [])
        client = _make_client()
        list(client.fetch_all())

        req_url = mock_arcgis.calls[0].request.url
        qs = parse_qs(urlparse(req_url).query)
        assert qs.get("outSR") == ["4326"]

    def test_http_error_raises(self, mock_arcgis):
        mock_arcgis.add(responses_lib.GET, ARCGIS_URL, status=500, body="Internal Server Error")
        client = _make_client()
        with pytest.raises(Exception):
            list(client.fetch_all())


# ---------------------------------------------------------------------------
# normalize() tests
# ---------------------------------------------------------------------------

VALID_FEATURE = _make_feature(
    objectid=1001,
    category="ASSAULT",
    offense="ASSAULT - SIMPLE",
    from_date_ms=1710469800000,  # 2024-03-15T02:30:00Z
    lat=32.7555,
    lon=-97.3208,
    beat="B11",
    division="EAST",
)


class TestNormalize:
    def test_normalize_valid_feature(self):
        rec = normalize(VALID_FEATURE)
        assert rec is not None
        assert isinstance(rec, NormalizedRecord)
        assert rec.raw_id == "1001"
        assert rec.category == "ASSAULT"
        assert rec.offense == "ASSAULT - SIMPLE"
        assert rec.lat == pytest.approx(32.7555)
        assert rec.lon == pytest.approx(-97.3208)
        assert rec.beat == "B11"
        assert rec.division == "EAST"
        assert rec.timestamp.tzinfo is not None

    def test_normalize_output_shape(self):
        rec = normalize(VALID_FEATURE)
        assert rec is not None
        for field in ("raw_id", "category", "offense", "timestamp", "lat", "lon", "beat", "division"):
            assert hasattr(rec, field), f"Missing field: {field}"

    def test_normalize_missing_lat_returns_none(self):
        feat = _make_feature(objectid=2, lat=None)
        assert normalize(feat) is None

    def test_normalize_missing_lon_returns_none(self):
        feat = _make_feature(objectid=3, lon=None)
        assert normalize(feat) is None

    def test_normalize_invalid_coords_out_of_bbox_lat(self):
        feat = _make_feature(objectid=4, lat=999)
        assert normalize(feat) is None

    def test_normalize_invalid_coords_out_of_bbox_lon(self):
        feat = _make_feature(objectid=5, lon=999)
        assert normalize(feat) is None

    def test_normalize_missing_date_returns_none(self):
        feat = _make_feature(objectid=6, from_date_ms=None)
        assert normalize(feat) is None

    def test_normalize_epoch_ms_parsed_correctly(self):
        rec = normalize(VALID_FEATURE)
        assert rec is not None
        assert rec.timestamp == datetime(2024, 3, 15, 2, 30, 0, tzinfo=timezone.utc)

    def test_normalize_batch_skips_malformed(self):
        results = [normalize(f) for f in MALFORMED_FEATURES]
        assert all(r is None for r in results), "All malformed features should normalize to None"

    def test_normalize_null_division_stored_as_none(self):
        feat = _make_feature(objectid=7, division=None)
        rec = normalize(feat)
        assert rec is not None
        assert rec.division is None
