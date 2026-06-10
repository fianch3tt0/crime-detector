from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from crime_detector.extensions import cache, db
from crime_detector.storage.repository import CrimeRepository

api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _crime_feature(crime) -> dict:
    from geoalchemy2.shape import to_shape

    point = to_shape(crime.geometry)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
        "properties": {
            "id": crime.id,
            "raw_id": crime.raw_id,
            "category": crime.category,
            "offense": crime.offense,
            "occurred_at": crime.occurred_at.isoformat(),
            "beat": crime.beat,
            "division": crime.division,
        },
    }


def _cluster_feature(row: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": row["geojson"],
        "properties": {
            "cluster": True,
            "count": row["count"],
            "categories": row["categories"],
        },
    }


@api_bp.route("/crimes")
@cache.cached(timeout=300, query_string=True)
def get_crimes():
    bbox_raw = request.args.get("bbox")
    bbox = _parse_bbox(bbox_raw)
    if bbox is None:
        return jsonify({"error": "Invalid or missing bbox parameter", "code": 400}), 400

    min_lon, min_lat, max_lon, max_lat = bbox

    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))

    if start and end and start > end:
        return jsonify({"error": "start must be before end", "code": 400}), 400

    repo = CrimeRepository(db.session)
    crimes = repo.query_bbox(min_lon, min_lat, max_lon, max_lat, start, end, None)
    features = [_crime_feature(c) for c in crimes]

    return jsonify(
        {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "count": len(features),
                "clustered": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    ), 200


@api_bp.route("/types")
@cache.cached(timeout=3600)
def get_types():
    repo = CrimeRepository(db.session)
    return jsonify({"types": repo.get_distinct_categories()})


@api_bp.route("/health")
def health():
    db_status = "ok"
    last_ingest = None
    crime_count = 0

    try:
        repo = CrimeRepository(db.session)
        last_ts = repo.get_last_ingest_timestamp()
        last_ingest = last_ts.isoformat() if last_ts else None
        crime_count = repo.count()
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        db_status = "error"

    return jsonify(
        {
            "status": "ok",
            "db": db_status,
            "last_ingest": last_ingest,
            "crime_count": crime_count,
        }
    )
