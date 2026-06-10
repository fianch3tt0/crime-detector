from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterator

import requests

logger = logging.getLogger(__name__)


class SodaClient:
    def __init__(self, endpoint: str, app_token: str = "", page_size: int = 1000) -> None:
        self.endpoint = endpoint
        self.app_token = app_token
        self.page_size = page_size
        self._session = requests.Session()
        if app_token:
            self._session.headers["X-App-Token"] = app_token

    def fetch_all(self, since: datetime | None = None) -> Iterator[dict]:
        """Page through the SODA endpoint, yielding raw record dicts.

        Adds a $where filter when `since` is provided so only newer records
        are returned (incremental pull).  Stops when a page is shorter than
        page_size, signalling the end of the dataset.
        """
        offset = 0
        while True:
            params = self._build_params(offset, since)
            page = self._get_page(params)
            yield from page
            if len(page) < self.page_size:
                break
            offset += self.page_size

    def _build_params(self, offset: int, since: datetime | None) -> dict:
        params: dict = {
            "$limit": self.page_size,
            "$offset": offset,
            "$order": "date ASC",
        }
        if since is not None:
            params["$where"] = f"date > '{since.isoformat()}'"
        return params

    def _get_page(self, params: dict) -> list[dict]:
        response = self._session.get(self.endpoint, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
