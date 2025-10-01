"""JSON mode tests for the legacy timestamp backfill utility.

Validates that the command-line interface when invoked with ``--json`` emits
well-structured machine-readable output for both the dry-run and apply phases.

We shell out to the module using ``python -m`` so that argument parsing and
entrypoint behavior are exercised (unlike the core logic tests which import
functions directly). A temporary SQLite database is created and seeded with
one naive and one aware timestamp per table, mirroring the setup in the
companion test file.

Assertions:
  * Dry-run JSON contains phase="dry_run" and correct per-table legacy counts.
  * Apply phase JSON contains phase="applied" with updated counts reflecting
	rewrites.
  * A second apply run shows zero legacy_naive remaining (idempotency) and
	zero additional updates.

The JSON schema (minimal contract enforced here):
{
  "phase": "dry_run" | "applied",
  "tables": [ {"table": str, "scanned": int, "legacy_naive": int, "updated": int}, ...],
  "totals": {"legacy_naive": int, "updated": int}
}
"""
from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argument list, no shell, controlled module invocation
import sys
import tempfile
from pathlib import Path
from typing import List

from crux_providers.persistence.sqlite.engine import create_connection, init_schema  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true  # type: ignore  # pragma: no cover

_assert = assert_true


def _seed(db_path: str) -> None:
	"""Create schema and insert one naive + one aware row per table."""
	conn = create_connection(db_path)
	init_schema(conn)
	conn.execute(
		"INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
		("openai", "gpt-4o", 123, None, None, 1, None, "2025-09-17T12:00:00.000000"),
	)
	conn.execute(
		"INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
		("openai", "gpt-4o", 50, None, None, 1, None, "2025-09-17T12:05:00.000000+00:00"),
	)
	conn.execute(
		"INSERT INTO chat_logs (provider, model, role_user, role_assistant, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
		("openai", "gpt-4o", "hi", "hello", "{}", "2025-09-17T12:10:00.000000"),
	)
	conn.execute(
		"INSERT INTO chat_logs (provider, model, role_user, role_assistant, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
		("openai", "gpt-4o", "ping", "pong", "{}", "2025-09-17T12:15:00.000000+00:00"),
	)
	conn.commit()
	conn.close()


def _run_cli(db_file: str, extra: List[str]) -> tuple[str, int]:
	"""Execute the backfill script as a module returning stdout text and exit code.

	Dry-run with legacy rows now exits with code 3 to allow CI gating. We do
	not use ``check=True`` so callers can assert on the explicit code.
	"""
	cmd = [
		sys.executable,
		"-m",
	"crux_providers.persistence.sqlite.backfill_timestamps",
		"--db",
		db_file,
	] + extra
	result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603 - fixed arg list
	return result.stdout.strip(), result.returncode


def _parse_single_json_block(output: str) -> dict:
	"""Return the JSON object from stdout.

	In JSON mode the script prints exactly one JSON document per invocation.
	"""
	return json.loads(output)


def test_json_dry_run_and_apply() -> None:
	"""Full-cycle test of JSON dry-run then apply then idempotent re-run."""
	with tempfile.TemporaryDirectory() as tmp:
		db_file = str(Path(tmp) / "providers.db")
		_seed(db_file)

		# Dry run
		dry_out, dry_code = _run_cli(db_file, ["--json"])
		# Expect exit code 3 (legacy rows detected) in dry-run.
		_assert(dry_code == 3, f"Expected exit code 3 for legacy dry-run, got {dry_code}")
		dry_data = _parse_single_json_block(dry_out)
		_assert(dry_data["phase"] == "dry_run", f"Unexpected phase: {dry_data}")
		tables = {t["table"]: t for t in dry_data["tables"]}
		_assert(tables["metrics"]["legacy_naive"] == 1, f"metrics legacy mismatch: {tables['metrics']}")
		_assert(tables["chat_logs"]["legacy_naive"] == 1, f"chat_logs legacy mismatch: {tables['chat_logs']}")
		_assert(dry_data["totals"]["legacy_naive"] == 2, f"total legacy mismatch: {dry_data['totals']}")

		# Apply pass (single JSON object now containing applied + embedded dry_run)
		apply_out, apply_code = _run_cli(db_file, ["--apply", "--yes", "--json"])
		_assert(apply_code == 0, f"Apply should exit 0, got {apply_code}")
		apply_data = _parse_single_json_block(apply_out)
		_assert(apply_data["phase"] == "applied", f"Unexpected apply phase: {apply_data}")
		_assert("dry_run" in apply_data, "Expected embedded dry_run data in applied payload")
		atables = {t["table"]: t for t in apply_data["tables"]}
		_assert(atables["metrics"]["updated"] == 1, f"metrics updated mismatch: {atables['metrics']}")
		_assert(atables["chat_logs"]["updated"] == 1, f"chat_logs updated mismatch: {atables['chat_logs']}")
		_assert(apply_data["totals"]["updated"] == 2, f"total updated mismatch: {apply_data['totals']}")
		# Ensure embedded dry_run totals mirror earlier scan
		_assert(apply_data["dry_run"]["totals"]["legacy_naive"] == 2, "Embedded dry_run total mismatch")

		# Idempotent re-run (applied with zero updates)
		second_out, second_code = _run_cli(db_file, ["--apply", "--yes", "--json"])
		_assert(second_code == 0, f"Second apply should exit 0, got {second_code}")
		second_data = _parse_single_json_block(second_out)
		stables = {t["table"]: t for t in second_data["tables"]}
		_assert(stables["metrics"]["legacy_naive"] == 0, f"metrics legacy after second apply: {stables['metrics']}")
		_assert(stables["chat_logs"]["legacy_naive"] == 0, f"chat_logs legacy after second apply: {stables['chat_logs']}")
		_assert(stables["metrics"]["updated"] == 0, "metrics should not update second time")
		_assert(stables["chat_logs"]["updated"] == 0, "chat_logs should not update second time")
		_assert(second_data["totals"]["updated"] == 0, "No overall updates expected in second apply run")


def test_zero_legacy_exit_code() -> None:
	"""Verify dry-run exit code is 0 when no legacy rows exist.

	Seeds only aware timestamps, then performs a JSON dry-run expecting:
	  * Exit code 0 (no legacy rows)
	  * totals.legacy_naive == 0
	"""
	with tempfile.TemporaryDirectory() as tmp:
		db_file = str(Path(tmp) / "providers.db")
		conn = create_connection(db_file)
		init_schema(conn)
		# Insert only aware timestamps
		conn.execute(
			"INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
			("openai", "gpt-4o", 50, None, None, 1, None, "2025-09-17T12:05:00.000000+00:00"),
		)
		conn.execute(
			"INSERT INTO chat_logs (provider, model, role_user, role_assistant, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
			("openai", "gpt-4o", "ping", "pong", "{}", "2025-09-17T12:15:00.000000+00:00"),
		)
		conn.commit()
		conn.close()

		out, code = _run_cli(db_file, ["--json"])
		_assert(code == 0, f"Expected exit code 0 when no legacy rows, got {code}")
		data = _parse_single_json_block(out)
	_assert(data["totals"]["legacy_naive"] == 0, f"Expected zero legacy rows: {data['totals']}")
