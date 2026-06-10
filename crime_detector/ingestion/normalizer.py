from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FORT_WORTH_BBOX = {
    "lat_min": 32.5,
    "lat_max": 33.1,
    "lon_min": -97.6,
    "lon_max": -97.0,
}


@dataclass
class NormalizedRecord:
    raw_id: str
    category: str
    offense: str
    timestamp: datetime
    lat: float
    lon: float
    beat: str | None
    division: str | None


def normalize(feature: dict) -> NormalizedRecord | None:
    """Map a raw ArcGIS GeoJSON feature to NormalizedRecord.

    Returns None for records with missing/invalid coordinates, unparseable
    dates, or missing OBJECTID so callers can skip them cleanly.
    """
    try:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}

        raw_id = str(props.get("OBJECTID") or "").strip()
        if not raw_id or raw_id == "0":
            return None

        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            return None

        try:
            lon, lat = float(coords[0]), float(coords[1])  # GeoJSON order: [lon, lat]
        except (TypeError, ValueError):
            return None

        bbox = FORT_WORTH_BBOX
        if not (bbox["lat_min"] <= lat <= bbox["lat_max"]):
            return None
        if not (bbox["lon_min"] <= lon <= bbox["lon_max"]):
            return None

        occurred_at = _parse_epoch_ms(props.get("From_Date"))
        if occurred_at is None:
            return None

        category = (props.get("Nature_Of_Call") or "UNKNOWN").strip().upper()
        offense = (props.get("Offense_Desc") or "UNKNOWN").strip().upper()
        beat = (props.get("Beat") or "").strip() or None
        division = (props.get("Division") or "").strip() or None

        return NormalizedRecord(
            raw_id=raw_id,
            category=category,
            offense=offense,
            timestamp=occurred_at,
            lat=lat,
            lon=lon,
            beat=beat,
            division=division,
        )
    except Exception:
        logger.debug("Failed to normalize feature: %s", feature, exc_info=True)
        return None


def _parse_epoch_ms(value) -> datetime | None:
    """ArcGIS Date fields arrive as integer epoch milliseconds."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
