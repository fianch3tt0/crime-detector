import pytest
import responses as responses_lib

from crime_detector import create_app

SODA_URL = "https://data.fortworthtexas.gov/resource/k6ic-7kp7.json"


def _make_record(
    raw_id="FW-001",
    category="ASSAULT",
    offense="ASSAULT - SIMPLE",
    date="2024-03-15T02:30:00",
    lat="32.7555",
    lon="-97.3208",
    beat="B11",
    sector="EAST",
):
    return {
        ":id": raw_id,
        "nature_of_call": category,
        "offense_description": offense,
        "date": date,
        "latitude": lat,
        "longitude": lon,
        "beat": beat,
        "sector": sector,
    }


SAMPLE_RECORDS = [_make_record(raw_id=f"FW-{i:03d}") for i in range(1, 6)]

MALFORMED_RECORDS = [
    _make_record(raw_id="FW-BAD-1", lat="", lon="-97.3208"),       # missing lat
    _make_record(raw_id="FW-BAD-2", lat="32.7555", lon=""),          # missing lon
    _make_record(raw_id="FW-BAD-3", lat="999", lon="-97.3208"),      # out-of-bbox lat
    _make_record(raw_id="FW-BAD-4", lat="32.7555", lon="999"),       # out-of-bbox lon
    _make_record(raw_id="FW-BAD-5", lat="abc", lon="-97.3208"),      # non-numeric lat
    _make_record(raw_id="FW-BAD-6", date="not-a-date"),              # unparseable date
]


@pytest.fixture
def flask_app():
    app = create_app("testing")
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def mock_soda():
    """Activate the responses mock library for SODA HTTP calls."""
    with responses_lib.RequestsMock() as rsps:
        yield rsps
