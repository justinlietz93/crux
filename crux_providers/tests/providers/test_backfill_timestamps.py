"""Tests for the legacy timestamp backfill utility.

Validates both dry-run scan (no updates) and apply mode rewriting naive
ISO8601 timestamps by appending an explicit UTC offset. The test creates a
real temporary SQLite database file (on disk) to exercise the script's path
resolution and connection behavior.

Scenarios covered:
  * Dry-run detects legacy naive rows in both tables and performs no updates.
  * Apply mode rewrites only legacy naive rows, leaving already-aware rows
	unchanged and making the operation idempotent on re-run.

Implementation Notes:
  * We import the internal functions (`backfill`, `_detect_legacy_naive`) for
	precise assertions instead of invoking the CLI entry (keeps test fast and
	deterministic while still covering core logic).
  * The engine schema default populates `created_at` via CURRENT_TIMESTAMP,
	which is already naive (no timezone). We explicitly insert crafted values
	to control the test surface.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from crux_providers.persistence.sqlite.engine import (
	create_connection,
	init_schema,
)
from crux_providers.persistence.sqlite.backfill_timestamps import (
	backfill,
	_detect_legacy_naive,
)
from crux_providers.tests.utils import assert_true

_assert = assert_true


def _setup_db(db_path: str) -> None:
	"""Initialize schema and seed controlled rows for both tables.

	We insert one legacy naive row and one already-aware row into each table to
	verify selective rewriting.
	"""
	conn = create_connection(db_path)
	init_schema(conn)

	# Metrics: (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at)
	conn.execute(
		"INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
		("openai", "gpt-4o", 123, None, None, 1, None, "2025-09-17T12:00:00.000000"),  # naive
	)
	conn.execute(
		"INSERT INTO metrics (provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
		("openai", "gpt-4o", 50, None, None, 1, None, "2025-09-17T12:05:00.000000+00:00"),  # aware
	)

	# Chat logs: (provider, model, role_user, role_assistant, metadata_json, created_at)
	conn.execute(
		"INSERT INTO chat_logs (provider, model, role_user, role_assistant, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
		("openai", "gpt-4o", "hi", "hello", "{}", "2025-09-17T12:10:00.000000"),  # naive
	)
	conn.execute(
		"INSERT INTO chat_logs (provider, model, role_user, role_assistant, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
		("openai", "gpt-4o", "ping", "pong", "{}", "2025-09-17T12:15:00.000000+00:00"),  # aware
	)

	conn.commit()
	conn.close()


def test_detect_legacy_naive_helper() -> None:
	"""Unit test for the detection heuristic covering representative cases."""
	_assert(_detect_legacy_naive("2025-01-01T00:00:00"), "Expected naive ISO to be detected")
	_assert(not _detect_legacy_naive("2025-01-01T00:00:00+00:00"), "Aware ISO should not be flagged")
	_assert(not _detect_legacy_naive("not-a-date"), "Malformed strings ignored")
	_assert(not _detect_legacy_naive(123), "Non-string values ignored")


def test_backfill_dry_run_and_apply() -> None:
	"""End-to-end test of dry-run reporting and apply selective rewrite.

	Steps:
	  1. Create temp DB and seed naive + aware rows.
	  2. Run dry-run (apply=False) -> expect legacy_naive counts of 1 per table, updated=0.
	  3. Run apply pass (apply=True) -> expect updated counts reflect only naive rows.
	  4. Re-run apply (idempotency) -> expect zero legacy_naive remaining.
	"""
	with tempfile.TemporaryDirectory() as tmp:
		db_file = str(Path(tmp) / "providers.db")
		_setup_db(db_file)

		# Dry-run scan
		reports = backfill(db_file, apply=False)
		tables = {r.table: r for r in reports}
		_assert(tables["metrics"].legacy_naive == 1, f"metrics legacy count mismatch: {tables['metrics']}")
		_assert(tables["metrics"].updated == 0, "metrics should not update in dry-run")
		_assert(tables["chat_logs"].legacy_naive == 1, f"chat_logs legacy count mismatch: {tables['chat_logs']}")
		_assert(tables["chat_logs"].updated == 0, "chat_logs should not update in dry-run")

		# Apply pass
		apply_reports = backfill(db_file, apply=True)
		apply_tables = {r.table: r for r in apply_reports}
		_assert(apply_tables["metrics"].updated == 1, f"metrics updated count mismatch: {apply_tables['metrics']}")
		_assert(apply_tables["chat_logs"].updated == 1, f"chat_logs updated count mismatch: {apply_tables['chat_logs']}")

		# Idempotent re-run
		second_apply = backfill(db_file, apply=True)
		second_tables = {r.table: r for r in second_apply}
		_assert(second_tables["metrics"].legacy_naive == 0, "No legacy metrics rows expected after rewrite")
		_assert(second_tables["chat_logs"].legacy_naive == 0, "No legacy chat_logs rows expected after rewrite")

		# Spot check DB content to ensure UTC suffix applied
		conn = create_connection(db_file)
		cur = conn.execute("SELECT created_at FROM metrics ORDER BY id")
		metric_times: List[str] = [row[0] for row in cur.fetchall()]
		_assert(metric_times[0].endswith("+00:00"), f"First metric timestamp not rewritten: {metric_times[0]}")
		_assert(metric_times[1].endswith("+00:00"), f"Aware metric timestamp unexpectedly altered: {metric_times[1]}")

		cur = conn.execute("SELECT created_at FROM chat_logs ORDER BY id")
		chat_times: List[str] = [row[0] for row in cur.fetchall()]
		_assert(chat_times[0].endswith("+00:00"), f"First chat timestamp not rewritten: {chat_times[0]}")
		_assert(chat_times[1].endswith("+00:00"), f"Aware chat timestamp unexpectedly altered: {chat_times[1]}")
		conn.close()
