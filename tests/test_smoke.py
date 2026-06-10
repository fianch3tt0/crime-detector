"""Phase 5 smoke tests: verify deployed app is reachable.

Set DEPLOYED_URL=https://your-app.example.com in your environment to run.
Tests are skipped automatically when the variable is absent so they never
fail in environments that haven't deployed yet.
"""
import os

import pytest
import requests

DEPLOYED_URL = os.environ.get("DEPLOYED_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not DEPLOYED_URL,
    reason="DEPLOYED_URL not set — skipping smoke tests",
)


def test_health_endpoint_responds():
    resp = requests.get(f"{DEPLOYED_URL}/api/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


def test_map_page_loads():
    resp = requests.get(DEPLOYED_URL + "/", timeout=10)
    assert resp.status_code == 200
    assert "leaflet" in resp.text.lower()
