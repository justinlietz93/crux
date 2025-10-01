from __future__ import annotations

import json

from crux_providers.service.cli import _plan_run, main


def test_cli_dry_run_plan_json(monkeypatch, capsys):
    # Basic dry-run should not raise and produce JSON
    code = main(["--provider", "openrouter"])  # no prompt, dry-run
    assert code == 0  # nosec B101
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["provider"] == "openrouter"  # nosec B101
    assert "streaming_supported" in data  # nosec B101


def test_plan_run_includes_capability_keys():
    plan = _plan_run(provider="openrouter", model=None, prompt="hi", stream=False)
    assert set(["provider", "model", "prompt_preview", "stream_requested", "adapter_available", "api_key_present", "streaming_supported"]) <= set(plan.keys())  # nosec B101
