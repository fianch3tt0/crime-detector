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


def normalize(raw: dict) -> NormalizedRecord | None:
    """Map a raw SODA record to NormalizedRecord.

    Returns None for records with missing/invalid coordinates or unparseable
    dates so callers can skip them cleanly.
    """
    try:
        raw_id = _extract_raw_id(raw)
        if not raw_id:
            return None

        lat, lon = _extract_coords(raw)
        if lat is None or lon is None:
            return None

        occurred_at = _parse_date(raw.get("date") or raw.get("occurred_at") or "")
        if occurred_at is None:
            return None

        category = (raw.get("nature_of_call") or raw.get("category") or "UNKNOWN").strip().upper()
        offense = (raw.get("offense_description") or raw.get("offense") or "UNKNOWN").strip().upper()
        beat = (raw.get("beat") or "").strip() or None
        division = (raw.get("sector") or raw.get("division") or "").strip() or None

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
        logger.debug("Failed to normalize record: %s", raw, exc_info=True)
        return None


def _extract_raw_id(raw: dict) -> str | None:
    for field in (":id", "caseid", "case_number", "objectid"):
        val = raw.get(field)
        if val:
            return str(val).strip()
    return None


def _extract_coords(raw: dict) -> tuple[float | None, float | None]:
    lat_raw = raw.get("latitude") or raw.get("lat")
    lon_raw = raw.get("longitude") or raw.get("lon")

    # SODA may also embed coords in a nested "location" dict
    if (lat_raw is None or lon_raw is None) and isinstance(raw.get("location"), dict):
        coords = raw["location"].get("coordinates")
        if isinstance(coords, list) and len(coords) == 2:
            lon_raw, lat_raw = coords[0], coords[1]

    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        return None, None

    bbox = FORT_WORTH_BBOX
    if not (bbox["lat_min"] <= lat <= bbox["lat_max"]):
        return None, None
    if not (bbox["lon_min"] <= lon <= bbox["lon_max"]):
        return None, None

    return lat, lon


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
