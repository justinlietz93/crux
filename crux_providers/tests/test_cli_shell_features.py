"""CLI shell regression tests for developer experience helpers."""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field

from crux_providers.base.models import ProviderMetadata
from crux_providers.service.cli.cli_shell import _execute_command, session_dispatch
from crux_providers.service.cli.cli_utils import format_metadata, parse_verbosity, suppress_console_logs


@dataclass
class _StubSession:
    """Minimal session double capturing chat and ask invocations."""

    chat_calls: list[str | None] = field(default_factory=list)
    ask_calls: list[str] = field(default_factory=list)

    def chat(self, prompt: str | None = None) -> None:
        """Record chat invocations for assertion."""

        self.chat_calls.append(prompt)

    def ask(self, prompt: str) -> None:
        """Record ask invocations for assertion."""

        self.ask_calls.append(prompt)

    # Placeholder implementations to satisfy dispatcher lookups
    def help(self) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def status(self) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def list_providers(self) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def use(self, _provider: str) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def set_model(self, _model: str | None) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def set_stream(self, *_args: str | None) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""

    def options(self, _tokens: list[str]) -> None:  # pragma: no cover - not exercised
        """Unused stub to satisfy dispatcher requirements."""


def test_parse_verbosity_accepts_synonyms() -> None:
    """Validate common synonyms resolve to canonical verbosity levels."""

    assert parse_verbosity("low") == "INFO"  # nosec B101
    assert parse_verbosity("verbose") == "DEBUG"  # nosec B101
    assert parse_verbosity("high") == "ERROR"  # nosec B101
    assert parse_verbosity("silent") == "CRITICAL"  # nosec B101


def test_session_dispatch_supports_inline_chat_prompts() -> None:
    """Ensure inline arguments are delivered to ``DevSession.chat``."""

    session = _StubSession()
    handled = session_dispatch(session, "chat", ["hello", "world"])
    assert handled  # nosec B101
    assert session.chat_calls == ["hello world"]  # nosec B101


def test_execute_command_falls_back_to_chat_on_unknown() -> None:
    """Unknown commands should fall back to chat execution."""

    session = _StubSession()
    _execute_command(session, "hello there")
    assert session.ask_calls == ["hello there"]  # nosec B101
    assert not session.chat_calls  # nosec B101


def test_format_metadata_table_renders_flat_keys() -> None:
    """Table mode should flatten metadata keys, including extras."""

    meta = ProviderMetadata(
        provider_name="unit",
        model_name="model-x",
        http_status=200,
        latency_ms=12.5,
        extra={"request_id": "req-1", "tokens": {"prompt": 1}},
    )
    rendered = format_metadata(meta, mode="table")
    lines = rendered.splitlines()
    assert any(line.startswith("provider_name") and "unit" in line for line in lines)  # nosec B101
    assert any(line.startswith("extra.request_id") and "req-1" in line for line in lines)  # nosec B101


def test_format_metadata_json_round_trip() -> None:
    """JSON mode should serialize metadata into a structured mapping."""

    meta = ProviderMetadata(provider_name="unit", model_name="model-y", http_status=201, latency_ms=None)
    payload = format_metadata(meta, mode="json")
    data = json.loads(payload)
    assert data["provider_name"] == "unit"  # nosec B101
    assert data["http_status"] == 201  # nosec B101


def test_suppress_console_logs_temporarily_detaches_handlers() -> None:
    """Console handlers should be muted during the suppression context."""

    base_logger = logging.getLogger("providers")
    original_handlers = list(base_logger.handlers)
    original_propagate = base_logger.propagate
    original_level = base_logger.level
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    base_logger.handlers[:] = [handler]
    base_logger.propagate = False
    base_logger.setLevel(logging.INFO)

    try:
        with suppress_console_logs():
            base_logger.info("hidden")
        handler.flush()
        assert stream.getvalue() == ""  # nosec B101

        base_logger.info("visible")
        handler.flush()
        assert "visible" in stream.getvalue()  # nosec B101
    finally:
        base_logger.handlers[:] = original_handlers
        base_logger.propagate = original_propagate
        base_logger.setLevel(original_level)
