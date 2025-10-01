from __future__ import annotations

from fastapi.testclient import TestClient

from crux_providers.service.app import app


def test_health_ok():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200  # nosec B101 test assertion
    data = r.json()
    assert data.get("ok") is True  # nosec B101 test assertion


# Optional: if a local/no-auth provider exists, add a minimal chat smoke.
# Here we skip to avoid requiring real API keys.


def test_metrics_summary_ok():
    client = TestClient(app)
    r = client.get("/api/metrics/summary")
    assert r.status_code == 200  # nosec B101 test assertion
    body = r.json()
    assert body.get("ok") is True  # nosec B101 test assertion
    summary = body.get("summary")
    assert isinstance(summary, dict)  # nosec B101 test assertion
    assert "total" in summary  # nosec B101 test assertion
