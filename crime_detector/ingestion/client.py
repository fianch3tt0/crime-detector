from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterator

import requests

logger = logging.getLogger(__name__)


class ArcGISClient:
    def __init__(self, endpoint: str, page_size: int = 1000) -> None:
        self.endpoint = endpoint
        self.page_size = page_size
        self._session = requests.Session()

    def fetch_all(self, since: datetime | None = None) -> Iterator[dict]:
        """Page through the ArcGIS Feature Layer, yielding raw GeoJSON feature dicts.

        Passes outSR=4326 on every request — the layer's native SR is WKID 2276
        (Texas State Plane, feet) and coordinates land in the Gulf without this.
        Stops when the response lacks exceededTransferLimit=true.
        """
        offset = 0
        while True:
            params = {
                "where": self._where_clause(since),
                "outFields": "*",
                "outSR": "4326",
                "f": "geojson",
                "resultRecordCount": self.page_size,
                "resultOffset": offset,
            }
            response = self._session.get(self.endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            features = data.get("features", [])
            yield from features
            if not data.get("exceededTransferLimit"):
                break
            offset += self.page_size

    def _where_clause(self, since: datetime | None) -> str:
        if since is None:
            return "1=1"
        ts = since.strftime("%Y-%m-%d %H:%M:%S")
        return f"From_Date > TIMESTAMP '{ts}'"
