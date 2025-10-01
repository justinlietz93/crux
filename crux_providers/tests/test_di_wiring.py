"""DI wiring tests for FastAPI provider service.

Clean, validated test file (reconstructed) verifying DI-based routes and
metrics summary endpoint after migration away from legacy helper.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from crux_providers.service.app import app, get_uow_dep
from crux_providers.base.models import ChatResponse, ProviderMetadata


@dataclass
class FakeMetric:
    provider: str
    model: str
    latency_ms: int
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    success: bool
    error_code: Optional[str]
    created_at: datetime


class FakeKeysRepo:
    def __init__(self) -> None:
        self._keys: Dict[str, str] = {}

    def get_api_key(self, provider: str) -> Optional[str]:
        return self._keys.get(provider)

    def set_api_key(self, provider: str, key: str) -> None:
        self._keys[provider] = key

    def delete_api_key(self, provider: str) -> None:  # pragma: no cover
        self._keys.pop(provider, None)

    def list_providers(self):  # pragma: no cover
        return sorted(self._keys.keys())


class FakePrefsRepo:
    def __init__(self) -> None:
        self.values: Dict[str, str] = {}

    def get_prefs(self):  # returns object with .values for compatibility
        @dataclass
        class P:
            values: Dict[str, str]
            updated_at: datetime

        return P(values=self.values, updated_at=datetime.now(timezone.utc))

    def set_prefs(self, values: Dict[str, str]):
        self.values = values
        return self.get_prefs()


class FakeMetricsRepo:
    def __init__(self) -> None:
        self.metrics: list[FakeMetric] = []

    def add_metric(self, entry: FakeMetric) -> None:
        self.metrics.append(entry)

    def aggregate_latency(self, provider: str, model: Optional[str] = None):  # pragma: no cover
        matches = [m for m in self.metrics if m.provider == provider and (model is None or m.model == model)]
        if not matches:
            return 0, 0
        return len(matches), int(sum(m.latency_ms for m in matches) / len(matches))

    def recent_errors(self, limit: int = 50):  # pragma: no cover
        return [m for m in self.metrics if not m.success][:limit]

    def summary(self) -> dict[str, Any]:
        # Ignore placeholder zero-latency metrics (e.g., synthetic chat route entries) to match
        # production summary filtering semantics.
        real_metrics = [m for m in self.metrics if m.latency_ms and m.latency_ms > 0]
        total = len(real_metrics)
        by_provider: Dict[str, list[int]] = {}
        for m in real_metrics:
            by_provider.setdefault(m.provider, []).append(m.latency_ms)
        by_provider_rows = [
            {
                "provider": p,
                "count": len(v),
                "avg_ms": float(sum(v) / len(v)) if v else None,
            }
            for p, v in sorted(by_provider.items(), key=lambda kv: len(kv[1]), reverse=True)
        ]
        by_model: Dict[str, list[int]] = {}
        for m in real_metrics:
            by_model.setdefault(m.model, []).append(m.latency_ms)
        by_model_rows = [
            {
                "model": p,
                "count": len(v),
                "avg_ms": float(sum(v) / len(v)) if v else None,
            }
            for p, v in sorted(by_model.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
        ]
        return {"total": total, "by_provider": by_provider_rows, "by_model": by_model_rows}


class FakeChatRepo:  # pragma: no cover
    def add(self, log):  # minimal stub
        return 1

    def get(self, chat_id: int):  # pragma: no cover
        return None

    def list_recent(self, limit: int = 100):  # pragma: no cover
        return []


class FakeUoW:
    def __init__(self) -> None:
        self.keys = FakeKeysRepo()
        self.prefs = FakePrefsRepo()
        self.metrics = FakeMetricsRepo()
        self.chats = FakeChatRepo()
        self._commits = 0

    def commit(self):
        self._commits += 1

    def rollback(self):  # pragma: no cover
        pass


fake_uow = FakeUoW()


def override_uow():
    return fake_uow


app.dependency_overrides[get_uow_dep] = override_uow
client = TestClient(app)


def test_keys_flow_via_uow():
    resp = client.post("/api/keys", json={"keys": {"OPENAI_API_KEY": "sk-test"}})  # pragma: allowlist secret - test placeholder value
    assert resp.status_code == 200  # nosec B101
    assert fake_uow.keys.get_api_key("openai") == "sk-test"  # nosec B101
    resp2 = client.get("/api/keys")
    assert resp2.status_code == 200  # nosec B101
    body = resp2.json()
    assert body["ok"] is True  # nosec B101
    assert body["keys"]["OPENAI_API_KEY"] is True  # nosec B101


def test_prefs_flow_via_uow():
    resp = client.post("/api/prefs", json={"prefs": {"theme": "dark"}})
    assert resp.status_code == 200  # nosec B101
    assert fake_uow.prefs.values["theme"] == "dark"  # nosec B101
    resp2 = client.get("/api/prefs")
    assert resp2.status_code == 200  # nosec B101
    assert resp2.json()["prefs"]["theme"] == "dark"  # nosec B101


class DummyAdapter:
    def chat(self, req):  # minimal stub
        meta = ProviderMetadata(
            provider_name="openai",
            model_name="gpt",
            extra={"usage": {"prompt_tokens": 5, "completion_tokens": 7}},
        )
        return ChatResponse(text="hi", parts=None, raw=None, meta=meta)


def test_chat_route_records_metric():
    from crux_providers.base.factory import ProviderFactory

    real_create = ProviderFactory.create

    def fake_create(provider: str):
        return DummyAdapter()

    ProviderFactory.create = staticmethod(fake_create)  # type: ignore
    try:
        body = {
            "provider": "openai",
            "model": "gpt",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        resp = client.post("/api/chat", json=body)
        assert resp.status_code == 200  # nosec B101
        assert len(fake_uow.metrics.metrics) == 1  # nosec B101
        m = fake_uow.metrics.metrics[0]
        assert m.provider == "openai"  # nosec B101
        assert m.tokens_prompt == 5 and m.tokens_completion == 7  # nosec B101
    finally:
        ProviderFactory.create = real_create


def test_metrics_summary_via_di():
    # Reset metrics to ensure deterministic count for this test
    fake_uow.metrics.metrics.clear()
    fake_uow.metrics.add_metric(
        FakeMetric(
            provider="openai",
            model="gpt-4o",
            latency_ms=120,
            tokens_prompt=None,
            tokens_completion=None,
            success=True,
            error_code=None,
            created_at=datetime.now(timezone.utc),
        )
    )
    fake_uow.metrics.add_metric(
        FakeMetric(
            provider="openai",
            model="gpt-4o",
            latency_ms=180,
            tokens_prompt=None,
            tokens_completion=None,
            success=True,
            error_code=None,
            created_at=datetime.now(timezone.utc),
        )
    )
    r = client.get("/api/metrics/summary")
    assert r.status_code == 200  # nosec B101
    data = r.json()
    summary = data.get("summary")
    assert summary and summary.get("total") == 2  # nosec B101
    providers = summary.get("by_provider") or []
    assert providers and providers[0]["provider"] == "openai"  # nosec B101
