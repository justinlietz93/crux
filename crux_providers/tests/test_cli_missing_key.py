"""CLI preflight tests: missing API key guidance and exit code.

Ensures that `providers.service.cli` exits with code 2 and prints a helpful
message listing acceptable environment variables when executing without an API
key present.
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO

import pytest

from crux_providers.service import cli as providers_cli


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        pytest.fail(msg)


def _clear_env(names):
    for n in names:
        if n in os.environ:
            del os.environ[n]


def test_cli_execute_missing_key_prints_hint_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure no keys are present
    _clear_env(["OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"])  # common ones

    # Capture stderr
    stderr = StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)

    # Execute with a provider likely present in mapping but without a key
    code = providers_cli.main(["run", "--provider", "openrouter", "--prompt", "hi", "--execute"])  # no stream
    _expect(code == 2, f"expected exit code 2, got {code}")

    # Validate stderr contains structured hint with acceptable env var names
    out = stderr.getvalue().strip()
    data = json.loads(out)
    _expect(data.get("error", "").startswith("missing API key"), f"unexpected error: {data}")
    _expect("OPENROUTER_API_KEY" in data.get("set_one_of_env", []), "OPENROUTER_API_KEY not suggested")
