import pytest
import responses as responses_lib

from crime_detector import create_app

ARCGIS_URL = "https://mapit.fortworthtexas.gov/ags/rest/services/CIVIC/Crime_Data/MapServer/0/query"


def _make_feature(
    objectid=1,
    category="ASSAULT",
    offense="ASSAULT - SIMPLE",
    from_date_ms=1710469800000,
    lat=32.7555,
    lon=-97.3208,
    beat="B11",
    division="EAST",
):
    return {
        "type": "Feature",
        "id": objectid,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "OBJECTID": objectid,
            "Nature_Of_Call": category,
            "Offense_Desc": offense,
            "From_Date": from_date_ms,
            "Beat": beat,
            "Division": division,
        },
    }


def _make_page(features, exceeded=False):
    """Wrap features in an ArcGIS GeoJSON FeatureCollection envelope."""
    resp = {"type": "FeatureCollection", "features": features}
    if exceeded:
        resp["exceededTransferLimit"] = True
    return resp


SAMPLE_FEATURES = [_make_feature(objectid=i) for i in range(1, 6)]

MALFORMED_FEATURES = [
    _make_feature(objectid=10, lat=None, lon=-97.3208),    # missing lat
    _make_feature(objectid=11, lat=32.7555, lon=None),     # missing lon
    _make_feature(objectid=12, lat=999, lon=-97.3208),     # out-of-bbox lat
    _make_feature(objectid=13, lat=32.7555, lon=999),      # out-of-bbox lon
    _make_feature(objectid=14, from_date_ms=None),         # missing date
]


@pytest.fixture
def flask_app():
    app = create_app("testing")
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def mock_arcgis():
    """Activate the responses mock library for ArcGIS HTTP calls."""
    with responses_lib.RequestsMock() as rsps:
        yield rsps
