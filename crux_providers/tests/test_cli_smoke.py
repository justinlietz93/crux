"""CLI smoke tests for providers debugging tool.

These tests validate the dry-run JSON output shape and the error path when
``--execute`` is used without providing a ``--prompt``. They do not perform
any network I/O and should be stable across environments.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from crux_providers.service import cli


def test_cli_dry_run_json_output(capsys) -> None:
    """Ensure the CLI prints valid JSON for the default dry-run invocation.

    The default invocation uses provider ``openrouter`` and prints a
    JSON plan describing the intended execution without performing network I/O.
    """
    exit_code = cli.main([])
    if exit_code != 0:
        raise AssertionError(f"expected exit 0, got {exit_code}")
    out = capsys.readouterr().out.strip()
    data: Dict[str, Any] = json.loads(out)
    # Validate minimal shape
    if "provider" not in data:
        raise AssertionError("missing 'provider' in CLI JSON output")
    if "adapter_available" not in data:
        raise AssertionError("missing 'adapter_available' in CLI JSON output")
    if "streaming_supported" not in data:
        raise AssertionError("missing 'streaming_supported' in CLI JSON output")


def test_cli_execute_requires_prompt(capsys) -> None:
    """Running with ``--execute`` but no ``--prompt`` should fail with code 2."""
    exit_code = cli.main(["--execute"])  # missing --prompt
    if exit_code != 2:
        raise AssertionError(f"expected exit 2 for missing prompt, got {exit_code}")
    err = capsys.readouterr().err.strip()
    if "--prompt is required" not in err:
        raise AssertionError("expected missing prompt error message in stderr")
