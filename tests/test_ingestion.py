"""Phase 1 tests: SodaClient paging + incremental pull, normalize()."""
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import responses as responses_lib

from crime_detector.ingestion.client import SodaClient
from crime_detector.ingestion.normalizer import NormalizedRecord, normalize
from tests.conftest import MALFORMED_RECORDS, SAMPLE_RECORDS, SODA_URL


# ---------------------------------------------------------------------------
# SodaClient tests
# ---------------------------------------------------------------------------

def _register_page(rsps, records, status=200):
    rsps.add(
        responses_lib.GET,
        SODA_URL,
        json=records,
        status=status,
    )


def _make_client(page_size=1000):
    return SodaClient(endpoint=SODA_URL, app_token="test-token", page_size=page_size)


class TestSodaClientPaging:
    def test_fetch_single_page(self, mock_soda):
        _register_page(mock_soda, SAMPLE_RECORDS)  # 5 records < page_size=1000 → stop
        client = _make_client()
        results = list(client.fetch_all())
        assert len(results) == 5

    def test_fetch_multi_page(self, mock_soda):
        page_size = 3
        page1 = SAMPLE_RECORDS[:3]   # full page → continue
        page2 = SAMPLE_RECORDS[3:5]  # partial page → stop
        _register_page(mock_soda, page1)
        _register_page(mock_soda, page2)
        client = _make_client(page_size=page_size)
        results = list(client.fetch_all())
        assert len(results) == 5

    def test_paging_stops_on_empty_page(self, mock_soda):
        _register_page(mock_soda, SAMPLE_RECORDS[:3])
        _register_page(mock_soda, [])
        client = _make_client(page_size=3)
        results = list(client.fetch_all())
        assert len(results) == 3

    def test_incremental_date_filter_sends_where_param(self, mock_soda):
        _register_page(mock_soda, [])
        since = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        client = _make_client()
        list(client.fetch_all(since=since))

        assert len(mock_soda.calls) == 1
        req_url = mock_soda.calls[0].request.url
        parsed = urlparse(req_url)
        qs = parse_qs(parsed.query)
        assert "$where" in qs
        assert "2024-01-15" in qs["$where"][0]

    def test_no_where_param_without_since(self, mock_soda):
        _register_page(mock_soda, [])
        client = _make_client()
        list(client.fetch_all(since=None))

        req_url = mock_soda.calls[0].request.url
        qs = parse_qs(urlparse(req_url).query)
        assert "$where" not in qs

    def test_app_token_header_sent(self, mock_soda):
        _register_page(mock_soda, [])
        client = SodaClient(endpoint=SODA_URL, app_token="my-token", page_size=1000)
        list(client.fetch_all())
        assert mock_soda.calls[0].request.headers.get("X-App-Token") == "my-token"

    def test_http_error_raises(self, mock_soda):
        mock_soda.add(responses_lib.GET, SODA_URL, status=500, body="Internal Server Error")
        client = _make_client()
        with pytest.raises(Exception):
            list(client.fetch_all())


# ---------------------------------------------------------------------------
# normalize() tests
# ---------------------------------------------------------------------------

VALID_RAW = {
    ":id": "FW-001",
    "nature_of_call": "ASSAULT",
    "offense_description": "ASSAULT - SIMPLE",
    "date": "2024-03-15T02:30:00",
    "latitude": "32.7555",
    "longitude": "-97.3208",
    "beat": "B11",
    "sector": "EAST",
}


class TestNormalize:
    def test_normalize_valid_record(self):
        rec = normalize(VALID_RAW)
        assert rec is not None
        assert isinstance(rec, NormalizedRecord)
        assert rec.raw_id == "FW-001"
        assert rec.category == "ASSAULT"
        assert rec.offense == "ASSAULT - SIMPLE"
        assert rec.lat == pytest.approx(32.7555)
        assert rec.lon == pytest.approx(-97.3208)
        assert rec.beat == "B11"
        assert rec.division == "EAST"
        assert rec.timestamp.tzinfo is not None

    def test_normalize_output_shape(self):
        rec = normalize(VALID_RAW)
        assert rec is not None
        for field in ("raw_id", "category", "offense", "timestamp", "lat", "lon", "beat", "division"):
            assert hasattr(rec, field), f"Missing field: {field}"

    def test_normalize_missing_lat_returns_none(self):
        raw = {**VALID_RAW, "latitude": ""}
        assert normalize(raw) is None

    def test_normalize_missing_lon_returns_none(self):
        raw = {**VALID_RAW, "longitude": ""}
        assert normalize(raw) is None

    def test_normalize_none_lat_returns_none(self):
        raw = {**VALID_RAW, "latitude": None}
        assert normalize(raw) is None

    def test_normalize_nonnumeric_lat_returns_none(self):
        raw = {**VALID_RAW, "latitude": "abc"}
        assert normalize(raw) is None

    def test_normalize_invalid_coords_out_of_bbox_lat(self):
        raw = {**VALID_RAW, "latitude": "999"}
        assert normalize(raw) is None

    def test_normalize_invalid_coords_out_of_bbox_lon(self):
        raw = {**VALID_RAW, "longitude": "999"}
        assert normalize(raw) is None

    def test_normalize_unparseable_date_returns_none(self):
        raw = {**VALID_RAW, "date": "not-a-date"}
        assert normalize(raw) is None

    def test_normalize_empty_date_returns_none(self):
        raw = {**VALID_RAW, "date": ""}
        assert normalize(raw) is None

    def test_normalize_nested_location_coords(self):
        raw = {k: v for k, v in VALID_RAW.items() if k not in ("latitude", "longitude")}
        raw["location"] = {"coordinates": [-97.3208, 32.7555]}
        rec = normalize(raw)
        assert rec is not None
        assert rec.lat == pytest.approx(32.7555)
        assert rec.lon == pytest.approx(-97.3208)

    def test_normalize_batch_skips_malformed(self):
        results = [normalize(r) for r in MALFORMED_RECORDS]
        assert all(r is None for r in results), "All malformed records should normalize to None"

    def test_normalize_caseid_field(self):
        raw = {**VALID_RAW}
        del raw[":id"]
        raw["caseid"] = "CASE-999"
        rec = normalize(raw)
        assert rec is not None
        assert rec.raw_id == "CASE-999"
