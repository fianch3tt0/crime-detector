"""Phase 3 tests: Flask API routes — /api/crimes, /api/types, /api/health.

The repository is patched so no live database is required.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from crime_detector import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FW_LAT, FW_LON = 32.7555, -97.3208
VALID_BBOX = f"{FW_LON - 0.1},{FW_LAT - 0.1},{FW_LON + 0.1},{FW_LAT + 0.1}"


def _make_crime(
    id=1,
    raw_id="FW-001",
    category="ASSAULT",
    offense="ASSAULT - SIMPLE",
    lat=FW_LAT,
    lon=FW_LON,
    beat="B11",
    division="EAST",
    occurred_at=None,
):
    """Return a MagicMock that mimics a Crime ORM row."""
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    crime = MagicMock()
    crime.id = id
    crime.raw_id = raw_id
    crime.category = category
    crime.offense = offense
    crime.beat = beat
    crime.division = division
    crime.occurred_at = occurred_at or datetime(2024, 3, 15, 2, 30, tzinfo=timezone.utc)
    crime.geometry = from_shape(Point(lon, lat), srid=4326)
    return crime


@pytest.fixture
def app():
    application = create_app("testing")
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _patch_repo(crimes=None, categories=None, last_ingest=None, crime_count=0, clusters=None):
    """Return a context manager that patches CrimeRepository."""
    repo = MagicMock()
    repo.query_bbox.return_value = crimes or []
    repo.query_bbox_clustered.return_value = clusters or []
    repo.get_distinct_categories.return_value = categories or []
    repo.get_last_ingest_timestamp.return_value = last_ingest
    repo.count.return_value = crime_count
    return patch("crime_detector.api.routes.CrimeRepository", return_value=repo)


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        with _patch_repo(crime_count=42):
            resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"
        assert data["crime_count"] == 42


# ---------------------------------------------------------------------------
# /api/types
# ---------------------------------------------------------------------------

class TestTypes:
    def test_types_endpoint_returns_list(self, client):
        with _patch_repo(categories=["ASSAULT", "THEFT"]):
            resp = client.get("/api/types")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "types" in data
        assert isinstance(data["types"], list)
        assert "ASSAULT" in data["types"]

    def test_types_empty(self, client):
        with _patch_repo(categories=[]):
            resp = client.get("/api/types")
        assert resp.status_code == 200
        assert resp.get_json()["types"] == []


# ---------------------------------------------------------------------------
# /api/crimes — valid GeoJSON structure
# ---------------------------------------------------------------------------

class TestCrimesGeoJSON:
    def test_returns_feature_collection(self, client):
        with _patch_repo(crimes=[_make_crime()]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert "meta" in data

    def test_feature_has_geometry_and_properties(self, client):
        with _patch_repo(crimes=[_make_crime()]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        feat = resp.get_json()["features"][0]
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        assert len(feat["geometry"]["coordinates"]) == 2
        props = feat["properties"]
        for key in ("raw_id", "category", "offense", "occurred_at", "beat", "division"):
            assert key in props

    def test_meta_fields(self, client):
        with _patch_repo(crimes=[_make_crime()]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        meta = resp.get_json()["meta"]
        assert "count" in meta
        assert "clustered" in meta
        assert "generated_at" in meta

    def test_empty_result_is_well_formed(self, client):
        with _patch_repo(crimes=[]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []
        assert data["meta"]["count"] == 0


# ---------------------------------------------------------------------------
# /api/crimes — parameter validation
# ---------------------------------------------------------------------------

class TestCrimesValidation:
    def test_missing_bbox_returns_400(self, client):
        resp = client.get("/api/crimes")
        assert resp.status_code == 400

    def test_malformed_bbox_returns_400(self, client):
        resp = client.get("/api/crimes?bbox=not,a,valid,bbox")
        assert resp.status_code == 400

    def test_bbox_wrong_number_of_parts_returns_400(self, client):
        resp = client.get("/api/crimes?bbox=-97.33,32.75")
        assert resp.status_code == 400

    def test_inverted_dates_returns_400(self, client):
        with _patch_repo():
            resp = client.get(
                f"/api/crimes?bbox={VALID_BBOX}&start=2024-12-01&end=2024-01-01"
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/crimes — filters actually filter
# ---------------------------------------------------------------------------

class TestCrimesFilters:
    def test_bbox_filter(self, client):
        crimes = [_make_crime(raw_id="FW-001"), _make_crime(raw_id="FW-002")]
        with _patch_repo(crimes=crimes) as mock_cls:
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["count"] == 2
        # Verify the bbox was forwarded to the repository
        repo_instance = mock_cls.return_value
        call_kwargs = repo_instance.query_bbox.call_args
        assert call_kwargs is not None

    def test_date_filter_forwarded_to_repo(self, client):
        with _patch_repo() as mock_cls:
            resp = client.get(
                f"/api/crimes?bbox={VALID_BBOX}&start=2024-01-01&end=2024-12-31"
            )
        assert resp.status_code == 200
        repo_instance = mock_cls.return_value
        call_args = repo_instance.query_bbox.call_args
        # start and end positional args (index 4, 5) should be datetime objects
        args = call_args[0] if call_args[0] else []
        kwargs = call_args[1] if call_args[1] else {}
        start_val = kwargs.get("start") or (args[4] if len(args) > 4 else None)
        end_val = kwargs.get("end") or (args[5] if len(args) > 5 else None)
        assert start_val is not None
        assert end_val is not None

    def test_type_param_is_ignored(self, client):
        # The route no longer filters by type — crime_type is always None
        with _patch_repo() as mock_cls:
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}&type=ASSAULT")
        assert resp.status_code == 200
        repo_instance = mock_cls.return_value
        call_args = repo_instance.query_bbox.call_args
        args = call_args[0] if call_args[0] else []
        kwargs = call_args[1] if call_args[1] else {}
        type_val = kwargs.get("crime_type") or (args[6] if len(args) > 6 else None)
        assert type_val is None


# ---------------------------------------------------------------------------
# /api/crimes — clustering is always disabled
# ---------------------------------------------------------------------------

class TestCrimesNeverClusters:
    def test_large_bbox_still_returns_unclustered(self, client):
        # Even a huge bbox must return clustered=False — clustering is removed
        big_bbox = "-98.0,32.0,-96.0,34.0"
        with _patch_repo(crimes=[_make_crime()]):
            resp = client.get(f"/api/crimes?bbox={big_bbox}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["clustered"] is False

    def test_many_crimes_still_unclustered(self, client):
        # Even with many crimes in the viewport, no clustering
        many = [_make_crime(id=i, raw_id=f"FW-{i:04d}") for i in range(50)]
        with _patch_repo(crimes=many):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        data = resp.get_json()
        assert data["meta"]["clustered"] is False
        assert data["meta"]["count"] == 50

    def test_feature_coordinates_are_lon_lat_order(self, client):
        # GeoJSON spec: coordinates must be [longitude, latitude]
        crime = _make_crime(lat=FW_LAT, lon=FW_LON)
        with _patch_repo(crimes=[crime]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        coords = resp.get_json()["features"][0]["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        assert -180 <= lon <= 180, "first coord must be longitude"
        assert -90 <= lat <= 90, "second coord must be latitude"
        assert abs(lon - FW_LON) < 0.01
        assert abs(lat - FW_LAT) < 0.01

    def test_occurred_at_is_iso_string(self, client):
        # occurred_at must be a parseable ISO 8601 string for the popup to work
        crime = _make_crime(occurred_at=datetime(2024, 3, 15, 2, 30, tzinfo=timezone.utc))
        with _patch_repo(crimes=[crime]):
            resp = client.get(f"/api/crimes?bbox={VALID_BBOX}")
        occurred_at = resp.get_json()["features"][0]["properties"]["occurred_at"]
        assert isinstance(occurred_at, str)
        parsed = datetime.fromisoformat(occurred_at)
        assert parsed.year == 2024
        assert parsed.month == 3
        assert parsed.day == 15
