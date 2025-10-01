"""Schema exposure tests for backfill_timestamps utility.

Validates that --print-schema emits a JSON document containing required top-level
fields and that a dry-run JSON output conforms to the declared shape (shallow
validation only; no external jsonschema dependency to keep stdlib-only).
"""
from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed arg list, no shell
import sys
import tempfile
from pathlib import Path

from crux_providers.persistence.sqlite.engine import create_connection, init_schema  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true  # type: ignore  # pragma: no cover

_assert = assert_true


def _run(args):
    cmd = [sys.executable, "-m", "crux_providers.persistence.sqlite.backfill_timestamps"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603 - fixed arg list
    return proc.returncode, proc.stdout.strip()


def test_print_schema_contains_expected_keys():
    code, out = _run(["--print-schema"])
    _assert(code == 0, f"--print-schema exit code unexpected: {code}")
    data = json.loads(out)
    for key in ("$schema", "title", "type", "properties"):
        _assert(key in data, f"Missing key in schema: {key}")
    # Ensure recursive reference for dry_run present
    _assert("dry_run" in data["properties"], "Schema missing dry_run property")


def test_dry_run_output_matches_schema_shape():
    with tempfile.TemporaryDirectory() as tmp:
        db_file = str(Path(tmp) / "providers.db")
        conn = create_connection(db_file)
        init_schema(conn)
        # Insert one naive row to force legacy detection
        conn.execute(
            "INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("openai", "gpt-4o", 123, None, None, 1, None, "2025-09-17T12:00:00.000000"),
        )
        conn.commit()
        conn.close()
        code, out = _run(["--json", "--db", db_file])
        _assert(code == 3, f"Expected exit code 3 for legacy rows, got {code}")
        payload = json.loads(out)
        for top in ("phase", "tables", "totals"):
            _assert(top in payload, f"Missing top-level key: {top}")
        _assert(payload["phase"] == "dry_run", f"Unexpected phase: {payload['phase']}")
        _assert(isinstance(payload["tables"], list), "tables should be list")
        _assert(isinstance(payload["totals"], dict), "totals should be dict")
        if payload["tables"]:
            sample = payload["tables"][0]
            for col in ("table", "scanned", "legacy_naive", "updated"):
                _assert(col in sample, f"Missing column key: {col}")
