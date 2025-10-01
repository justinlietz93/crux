"""Unit tests for Ollama CLI table parsing.

Validates robust parsing of ``ollama list`` human-readable output across
spacing variations and with/without headers.
"""

from __future__ import annotations

from crux_providers.ollama import get_ollama_models as gom
from crux_providers.ollama.get_ollama_models import _parse_ollama_list_table


def test_parse_with_header_multiple_spaces() -> None:
    """Parser handles standard header and variable spacing within columns."""
    sample = (
        "NAME            ID                         SIZE    MODIFIED\n"
        "llama3.1:8b     sha256:abc123               4.1 GB  2 weeks ago\n"
        "qwen2.5:14b     sha256:def456               7.8 GB  3 days ago\n"
    )

    items = _parse_ollama_list_table(sample)

    assert len(items) == 2
    assert items[0]["name"] == "llama3.1:8b"
    assert items[0]["id"] == "llama3.1:8b"
    assert items[0]["id_digest"] == "sha256:abc123"
    assert items[0]["size"] == "4.1 GB"
    assert items[0]["modified"] == "2 weeks ago"

    assert items[1]["name"] == "qwen2.5:14b"
    assert items[1]["id_digest"] == "sha256:def456"
    assert items[1]["size"] == "7.8 GB"
    assert items[1]["modified"] == "3 days ago"


def test_parse_without_header_assumes_first_column_name() -> None:
    """Parser tolerates outputs without a header by using first column as name."""
    sample = (
        "llama3.1:8b     sha256:abc123               4.1 GB  2 weeks ago\n"
        "qwen2.5:14b     sha256:def456               7.8 GB  3 days ago\n"
    )

    items = _parse_ollama_list_table(sample)
    assert len(items) == 2
    assert items[0]["name"] == "llama3.1:8b"
    assert items[0]["id"] == "llama3.1:8b"
    # Without header, extra fields may be absent; ensure graceful presence of essentials
    assert set(items[0].keys()) >= {"id", "name"}


def test_run_uses_http_fallback_when_cli_missing(monkeypatch) -> None:
    """HTTP fallback is used when the CLI is unavailable."""

    def fake_cli() -> list[dict[str, str]]:
        raise FileNotFoundError("ollama missing")

    http_models = [{"id": "llama3", "name": "llama3"}]

    def fake_http() -> list[dict[str, str]]:
        return http_models

    def fake_save(provider: str, models, *, fetched_via: str, metadata: dict) -> None:
        assert provider == "ollama"
        assert fetched_via == "ollama_http"
        assert metadata["source"] == "ollama_http"

    class _SentinelSnapshot:
        def __init__(self) -> None:  # pragma: no cover - defensive guard
            raise AssertionError("cache should not be used when HTTP succeeds")

    monkeypatch.setattr(gom, "_fetch_via_cli", fake_cli)
    monkeypatch.setattr(gom, "_fetch_via_http_api", fake_http)
    monkeypatch.setattr(gom, "save_provider_models", fake_save)
    monkeypatch.setattr(gom, "load_cached_models", lambda provider: _SentinelSnapshot())

    models = gom.run()
    assert models == http_models


def test_fetch_via_http_api_normalizes_entries(monkeypatch) -> None:
    """HTTP API payloads are normalized to include id/name pairs."""

    payload = {"models": [{"model": "llama3", "digest": "sha256:abc", "size": "4 GB"}]}

    class DummyResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._data

    class DummyClient:
        def __init__(self, data):
            self._data = data

        def get(self, path):
            assert path == "/api/tags"
            return DummyResponse(self._data)

    monkeypatch.setattr(gom, "get_httpx_client", lambda base_url, purpose: DummyClient(payload))
    monkeypatch.setattr(gom, "get_provider_config", lambda provider: {"host": "http://127.0.0.1:11434"})

    items = gom._fetch_via_http_api()
    assert items[0]["id"] == "llama3"
    assert items[0]["name"] == "llama3"
    assert items[0]["digest"] == "sha256:abc"
