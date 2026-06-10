"""Phase 2 tests: CrimeRepository — upsert, dedup, spatial queries.

Requires a live PostgreSQL + PostGIS instance.  Set TEST_DATABASE_URL in your
environment (or .env) to run.  Tests are skipped automatically when no database
is reachable so they never block CI environments without a DB.
"""
import os
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from crime_detector.ingestion.normalizer import NormalizedRecord
from crime_detector.models import Base
from crime_detector.storage.repository import CrimeRepository

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set — skipping storage tests",
)


def _check_db_reachable(url: str) -> bool:
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def db_engine():
    if not _check_db_reachable(TEST_DATABASE_URL):
        pytest.skip("Cannot connect to test database")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def repo(db_session):
    return CrimeRepository(db_session)


def _record(
    raw_id="FW-001",
    category="ASSAULT",
    offense="ASSAULT - SIMPLE",
    lat=32.7555,
    lon=-97.3208,
    beat="B11",
    division="EAST",
    occurred_at=None,
):
    return NormalizedRecord(
        raw_id=raw_id,
        category=category,
        offense=offense,
        timestamp=occurred_at or datetime(2024, 3, 15, 2, 30, tzinfo=timezone.utc),
        lat=lat,
        lon=lon,
        beat=beat,
        division=division,
    )


class TestInsertAndUpsert:
    def test_insert_single(self, repo, db_session):
        repo.upsert_batch([_record()])
        crimes = repo.query_bbox(-97.4, 32.6, -97.2, 32.9)
        assert len(crimes) == 1
        assert crimes[0].raw_id == "FW-001"
        assert crimes[0].category == "ASSAULT"

    def test_upsert_dedup_raw_id(self, repo, db_session):
        repo.upsert_batch([_record(raw_id="DUP-001")])
        repo.upsert_batch([_record(raw_id="DUP-001")])
        crimes = repo.query_bbox(-97.4, 32.6, -97.2, 32.9)
        assert sum(1 for c in crimes if c.raw_id == "DUP-001") == 1

    def test_upsert_updates_fields(self, repo, db_session):
        repo.upsert_batch([_record(raw_id="UPD-001", category="THEFT")])
        repo.upsert_batch([_record(raw_id="UPD-001", category="ASSAULT")])
        crimes = repo.query_bbox(-97.4, 32.6, -97.2, 32.9)
        match = next(c for c in crimes if c.raw_id == "UPD-001")
        assert match.category == "ASSAULT"


class TestSpatialQuery:
    def test_spatial_bbox_query_filters_outside(self, repo, db_session):
        inside1 = _record(raw_id="IN-001", lat=32.76, lon=-97.33)
        inside2 = _record(raw_id="IN-002", lat=32.77, lon=-97.32)
        outside = _record(raw_id="OUT-001", lat=32.50, lon=-97.00)  # outside query bbox
        repo.upsert_batch([inside1, inside2, outside])

        # Query a tight bbox that catches inside1+2 but not outside
        results = repo.query_bbox(-97.40, 32.70, -97.30, 32.80)
        raw_ids = {c.raw_id for c in results}
        assert "IN-001" in raw_ids
        assert "IN-002" in raw_ids
        assert "OUT-001" not in raw_ids

    def test_date_filter_start(self, repo, db_session):
        early = _record(raw_id="DATE-001", occurred_at=datetime(2023, 1, 1, tzinfo=timezone.utc))
        late = _record(raw_id="DATE-002", occurred_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
        repo.upsert_batch([early, late])

        results = repo.query_bbox(
            -97.4, 32.6, -97.2, 32.9,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        raw_ids = {c.raw_id for c in results}
        assert "DATE-002" in raw_ids
        assert "DATE-001" not in raw_ids

    def test_date_filter_end(self, repo, db_session):
        early = _record(raw_id="END-001", occurred_at=datetime(2023, 6, 1, tzinfo=timezone.utc))
        late = _record(raw_id="END-002", occurred_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
        repo.upsert_batch([early, late])

        results = repo.query_bbox(
            -97.4, 32.6, -97.2, 32.9,
            end=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        raw_ids = {c.raw_id for c in results}
        assert "END-001" in raw_ids
        assert "END-002" not in raw_ids

    def test_type_filter(self, repo, db_session):
        repo.upsert_batch([
            _record(raw_id="TYPE-001", category="THEFT"),
            _record(raw_id="TYPE-002", category="ASSAULT"),
        ])
        results = repo.query_bbox(-97.4, 32.6, -97.2, 32.9, crime_type="THEFT")
        raw_ids = {c.raw_id for c in results}
        assert "TYPE-001" in raw_ids
        assert "TYPE-002" not in raw_ids


class TestMetaQueries:
    def test_get_last_ingest_timestamp(self, repo, db_session):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        repo.upsert_batch([
            _record(raw_id="TS-001", occurred_at=t1),
            _record(raw_id="TS-002", occurred_at=t2),
        ])
        last = repo.get_last_ingest_timestamp()
        assert last is not None
        assert last.replace(tzinfo=timezone.utc) >= t2

    def test_get_last_ingest_timestamp_empty(self, repo):
        last = repo.get_last_ingest_timestamp()
        assert last is None

    def test_get_distinct_categories(self, repo, db_session):
        repo.upsert_batch([
            _record(raw_id="CAT-001", category="THEFT"),
            _record(raw_id="CAT-002", category="ASSAULT"),
            _record(raw_id="CAT-003", category="THEFT"),
        ])
        cats = repo.get_distinct_categories()
        assert "THEFT" in cats
        assert "ASSAULT" in cats
        assert cats == sorted(cats)
