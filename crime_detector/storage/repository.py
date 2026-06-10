from __future__ import annotations

import logging
from datetime import datetime

from geoalchemy2.functions import ST_MakeEnvelope, ST_Within
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from crime_detector.ingestion.normalizer import NormalizedRecord
from crime_detector.models import Crime

logger = logging.getLogger(__name__)


class CrimeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def upsert_batch(self, records: list[NormalizedRecord]) -> dict[str, int]:
        """Bulk upsert using INSERT ... ON CONFLICT (raw_id) DO UPDATE."""
        if not records:
            return {"inserted": 0, "updated": 0}

        rows = [
            {
                "raw_id": r.raw_id,
                "category": r.category,
                "offense": r.offense,
                "occurred_at": r.timestamp,
                "beat": r.beat,
                "division": r.division,
                "geometry": f"SRID=4326;POINT({r.lon} {r.lat})",
            }
            for r in records
        ]

        stmt = pg_insert(Crime).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["raw_id"],
            set_={
                "category": stmt.excluded.category,
                "offense": stmt.excluded.offense,
                "occurred_at": stmt.excluded.occurred_at,
                "beat": stmt.excluded.beat,
                "division": stmt.excluded.division,
                "geometry": stmt.excluded.geometry,
                "updated_at": func.now(),
            },
        )
        result = self._session.execute(stmt)
        self._session.commit()

        # rowcount on an upsert reflects rows affected (inserted + updated)
        rows_affected = result.rowcount
        return {"inserted": rows_affected, "updated": 0}

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def query_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        start: datetime | None = None,
        end: datetime | None = None,
        crime_type: str | None = None,
        limit: int = 5000,
    ) -> list[Crime]:
        envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = select(Crime).where(ST_Within(Crime.geometry, envelope))

        if start is not None:
            stmt = stmt.where(Crime.occurred_at >= start)
        if end is not None:
            stmt = stmt.where(Crime.occurred_at <= end)
        if crime_type is not None:
            stmt = stmt.where(Crime.category.ilike(f"%{crime_type}%"))

        stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())

    def query_bbox_clustered(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        start: datetime | None = None,
        end: datetime | None = None,
        crime_type: str | None = None,
    ) -> list[dict]:
        """Return grid-snapped cluster aggregates for the given bbox."""
        bbox_width = max_lon - min_lon
        grid_size = bbox_width / 20.0

        conditions = [
            "ST_Within(geometry, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        ]
        params: dict = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "grid_size": grid_size,
        }

        if start is not None:
            conditions.append("occurred_at >= :start")
            params["start"] = start
        if end is not None:
            conditions.append("occurred_at <= :end")
            params["end"] = end
        if crime_type is not None:
            conditions.append("category ILIKE :crime_type")
            params["crime_type"] = f"%{crime_type}%"

        where_clause = " AND ".join(conditions)

        sql = text(f"""
            SELECT
                ST_X(ST_Centroid(ST_Collect(cell))) AS lon,
                ST_Y(ST_Centroid(ST_Collect(cell))) AS lat,
                SUM(cat_count)                      AS total,
                json_object_agg(category, cat_count) AS categories
            FROM (
                SELECT
                    ST_SnapToGrid(geometry, :grid_size) AS cell,
                    category,
                    COUNT(*)                            AS cat_count
                FROM crimes
                WHERE {where_clause}
                GROUP BY cell, category
            ) sub
            GROUP BY cell
        """)

        rows = self._session.execute(sql, params).fetchall()
        return [
            {
                "geojson": {"type": "Point", "coordinates": [float(row.lon), float(row.lat)]},
                "count": int(row.total),
                "categories": row.categories if isinstance(row.categories, dict) else {},
            }
            for row in rows
        ]

    def get_last_ingest_timestamp(self) -> datetime | None:
        result = self._session.execute(select(func.max(Crime.occurred_at))).scalar()
        return result

    def get_distinct_categories(self) -> list[str]:
        rows = self._session.execute(
            select(Crime.category).distinct().order_by(Crime.category)
        ).scalars().all()
        return list(rows)

    def count(self) -> int:
        return self._session.execute(select(func.count(Crime.id))).scalar() or 0
