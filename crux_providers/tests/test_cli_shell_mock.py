"""Integration-style tests ensuring the CLI shell works with mock providers."""

from __future__ import annotations

import pytest

from crux_providers.service.cli.cli_shell import DevSession


@pytest.mark.usefixtures("enable_mock_providers")
def test_dev_session_ask_uses_mock_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    """The developer shell should emit mock responses when the toggle is enabled."""

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    session = DevSession(provider="openai", model=None, stream=False, live=False)
    session.ask("hello")
    captured = capsys.readouterr()
    assert "Hello from the mock provider!" in captured.out
    assert "metadata" in captured.out
