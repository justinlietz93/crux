"""Utility script to normalize legacy naive `created_at` timestamps.

Purpose
-------
Legacy deployments may contain rows in `metrics` and `chat_logs` tables where
`created_at` was inserted via SQLite's implicit CURRENT_TIMESTAMP handling or
through older code paths that produced naive datetimes serialized without an
explicit UTC offset. Current repository logic (see `repos._parse_created_at`)
coerces these values to UTC on read, but leaving them in-place obscures the
true storage policy (ISO8601 + explicit offset) and makes external inspection
or downstream ETL normalization ambiguous.

This script performs a safe, transactional rewrite of those legacy rows.

Behavior
--------
* By default performs a DRY-RUN (no data changes) and reports counts.
* Detection heuristic: A value is considered "legacy naive" if ALL apply:
  - Column type is string (Python `str`).
  - `datetime.fromisoformat(value)` succeeds.
  - Parsed datetime is naive (`tzinfo is None`).
* Rewrite format: `value` -> `value + '+00:00'` via converting the parsed
  naive datetime to `dt.replace(tzinfo=timezone.utc).isoformat()`.
* Tables processed: `metrics`, `chat_logs` (skips silently if absent).
* Wraps updates in a single transaction; partial updates are rolled back on
  error.

Usage
-----
python -m productivity_tools.crux_providers.persistence.sqlite.backfill_timestamps \
    --db /path/to/providers.db            # optional custom path
    [--apply]                             # perform the update
    [--yes]                               # skip interactive confirmation when applying
    [--print-schema]                      # emit JSON schema for --json output and exit

Exit Codes
----------
0 success (no legacy rows or applied updates)
1 unexpected error / exception
2 user aborted (confirmation declined)
3 legacy rows detected during dry-run (no changes performed) – enables CI gating

Design Notes
------------
* No external dependencies; pure stdlib for portability.
* Idempotent: Re-running after successful application finds 0 legacy rows.
* Conservative: Only updates rows whose current value is demonstrably naive.
* Performs per-row parameterized UPDATEs; for very large tables a batched
  approach could be introduced, but simplicity favored for current scale.

"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .engine import create_connection, init_schema, get_db_path

@dataclass
class TableReport:
    """Per-table scan/update accounting.

    Attributes
    ----------
    table : str
        Logical table name (e.g., `metrics`, `chat_logs`).
    scanned : int
        Number of rows examined in the table.
    legacy_naive : int
        Count of rows whose `created_at` was detected as legacy naive.
    updated : int
        Count of rows rewritten during apply phase (0 during dry-run).

    Notes
    -----
    Instances of this dataclass are aggregated to compute totals and are
    serialized via `_reports_to_dict()` for JSON emission.
    """
    table: str
    scanned: int
    legacy_naive: int
    updated: int = 0

    def to_row(self) -> str:
        return f"{self.table:10} | {self.scanned:7} | {self.legacy_naive:12} | {self.updated:7}"

HEADER = "TABLE      | SCANNED | LEGACY_NAIVE | UPDATED "
SEP = "-" * len(HEADER)

# JSON Schema for emitted --json payloads (dry_run or applied). Maintained inline to
# allow tooling (CI, external integrations) to fetch via --print-schema without
# importing third-party schema packages.
_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "BackfillTimestampReport",
    "type": "object",
    "required": ["phase", "tables", "totals"],
    "properties": {
        "phase": {"type": "string", "enum": ["dry_run", "applied"]},
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["table", "scanned", "legacy_naive", "updated"],
                "properties": {
                    "table": {"type": "string"},
                    "scanned": {"type": "integer", "minimum": 0},
                    "legacy_naive": {"type": "integer", "minimum": 0},
                    "updated": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        },
        "totals": {
            "type": "object",
            "required": ["legacy_naive", "updated"],
            "properties": {
                "legacy_naive": {"type": "integer", "minimum": 0},
                "updated": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        # Embedded dry_run object only present for applied payloads; we make it optional and recursive.
        "dry_run": {"$ref": "#"},
    },
    "additionalProperties": False,
}


def _detect_legacy_naive(value) -> bool:
    """Return True if the input is a naive ISO8601 datetime string.

    A value qualifies as "legacy naive" when all conditions hold:
    - It is a `str` instance.
    - `datetime.fromisoformat(value)` succeeds.
    - The parsed `datetime` is naive (`tzinfo is None`).

    Parameters
    ----------
    value : Any
        Candidate value from the `created_at` column.

    Returns
    -------
    bool
        True when value is a naive ISO8601 string; otherwise False.
    """
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return False
    return dt.tzinfo is None


def _rewrite(value: str) -> str:
    """Normalize a datetime string to an explicit UTC ISO8601 representation.

    If the parsed value is naive, its `tzinfo` is set to UTC prior to
    serialization; if already aware, the original timezone is preserved.

    Parameters
    ----------
    value : str
        Original datetime string stored in the database.

    Returns
    -------
    str
        ISO8601 string with explicit timezone, typically `+00:00` for UTC.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _process_table(conn: sqlite3.Connection, table: str, apply: bool) -> TableReport:
    """Scan a table for legacy naive timestamps and optionally rewrite them.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open SQLite connection.
    table : str
        Table name to process (`metrics` or `chat_logs`).
    apply : bool
        When True, perform in-place updates inside the active transaction.

    Returns
    -------
    TableReport
        Per-table accounting (scanned, legacy-naive count, updated count).
    """
    # Determine presence
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    )
    if not cur.fetchone():
        return TableReport(table=table, scanned=0, legacy_naive=0, updated=0)

    cur = conn.execute(f"SELECT id, created_at FROM {table}")  # nosec - table name controlled
    rows = cur.fetchall()
    report = TableReport(table=table, scanned=len(rows), legacy_naive=0, updated=0)
    for row_id, created_at in rows:
        if _detect_legacy_naive(created_at):
            report.legacy_naive += 1
            if apply:
                conn.execute(
                    f"UPDATE {table} SET created_at = ? WHERE id = ?",  # nosec - table validated
                    (_rewrite(created_at), row_id),
                )
                report.updated += 1
    return report


def backfill(db_path: Optional[str], apply: bool) -> List[TableReport]:
    """Perform a dry-run scan or an apply pass over target tables.

    This helper ensures the schema exists, processes supported tables, and
    commits the transaction when `apply` is True.

    Parameters
    ----------
    db_path : str | None
        Optional explicit path to the providers database; when None the
        standard path from `get_db_path()` is used.
    apply : bool
        When True, rewrite naive timestamps to explicit UTC.

    Returns
    -------
    list[TableReport]
        Reports in table order: metrics, chat_logs.
    """
    path = get_db_path(db_path)
    conn = create_connection(str(path))
    try:
        init_schema(conn)  # ensure tables exist (harmless if already present)
        reports = [
            _process_table(conn, table, apply) for table in ("metrics", "chat_logs")
        ]
        if apply:
            conn.commit()
        return reports
    finally:
        conn.close()


def _print_reports(title: str, reports: List[TableReport]) -> None:
    """Print a human-readable table to stdout summarizing per-table results.

    Parameters
    ----------
    title : str
        Section header printed above the table.
    reports : list[TableReport]
        Per-table results to render.

    Side Effects
    ------------
    Writes to standard output; intended for interactive/operator use.
    """
    print(f"\n{title}")
    print(HEADER)
    print(SEP)
    for rep in reports:
        print(rep.to_row())
    print(SEP)


def _reports_to_dict(phase: str, reports: List[TableReport]) -> dict:
    """Convert a list of TableReport objects into a serializable mapping.

    Parameters
    ----------
    phase: str
        Logical phase label (e.g., "dry_run", "applied").
    reports: list[TableReport]
        Collected table reports.

    Returns
    -------
    dict
        Mapping containing phase, per-table details, and aggregate totals.
    """
    total_legacy = sum(r.legacy_naive for r in reports)
    total_updated = sum(r.updated for r in reports)
    return {
        "phase": phase,
        "tables": [
            {
                "table": r.table,
                "scanned": r.scanned,
                "legacy_naive": r.legacy_naive,
                "updated": r.updated,
            }
            for r in reports
        ],
        "totals": {
            "legacy_naive": total_legacy,
            "updated": total_updated,
        },
    }



def _confirm_apply(args, total_legacy: int) -> int:
    """Handle pre-apply validation and optional confirmation.

    Returns a non-zero exit code for early termination scenarios; 0 to proceed.
    """
    if total_legacy == 0:
        if not args.json:
            print("--apply specified but no legacy rows found; exiting.")
        return 1
    if not args.yes and not args.json:
        confirm = input("Proceed with in-place update of the counts above? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            if not args.json:
                print("Aborted by user.")
            return 2
    return 0


def _apply_phase(db_path: Optional[str], json_mode: bool) -> List[TableReport]:
    """Execute the apply phase returning update reports."""
    path = get_db_path(db_path)
    conn = create_connection(str(path))
    try:
        update_reports = [
            _process_table(conn, table, apply=True) for table in ("metrics", "chat_logs")
        ]
        conn.commit()
        return update_reports
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    """Parse CLI arguments for the backfill utility.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument vector for testing.

    Returns
    -------
    argparse.Namespace
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Normalize legacy naive timestamps to UTC aware ISO8601."
    )
    parser.add_argument(
        "--db", dest="db_path", help="Path to providers.db (defaults to standard path)"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (otherwise dry-run)"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip interactive confirmation when applying"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary (dry-run and, if applied, final phase)",
    )
    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print JSON schema describing --json output then exit",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:  # noqa: C901 - structured via helpers
    """Command-line entrypoint.

    Orchestrates two phases:
    1. Dry-run scan (always executed) reporting counts of legacy naive timestamps.
    2. Optional apply phase (when --apply is provided) performing in-place
       normalization, guarded by confirmation unless --yes or --json is set.

    JSON Mode:
        When --json is supplied, machine-readable summaries for the dry-run
        (phase="dry_run") and, if performed, the apply phase (phase="applied")
        are emitted. This enables automation tooling to parse outcomes without
        scraping console tables.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument vector for testing; defaults to sys.argv when None.

    Returns
    -------
    int
        POSIX exit code (0 success, 2 user abort).
    """
    args = _parse_args(argv)

    if getattr(args, "print_schema", False):  # early exit for tooling
        print(json.dumps(_SCHEMA, indent=2))
        return 0

    # Phase 1: Dry-run scan
    reports = backfill(args.db_path, apply=False)
    total_legacy = sum(r.legacy_naive for r in reports)
    if args.json and not args.apply:
        # JSON dry-run only: emit single object
        print(json.dumps(_reports_to_dict("dry_run", reports), indent=2))
    elif not args.json:
        _print_reports("Legacy Timestamp Backfill (Dry-Run Scan)", reports)
        print(f"TOTAL      |         | {total_legacy:12} |")
        if not args.apply:
            if total_legacy == 0:
                print("No legacy naive timestamps detected; nothing to do.")
            else:
                print("Re-run with --apply (and optionally --yes) to rewrite naive values.")
    if not args.apply:
        # Introduce exit code 3 when legacy rows are detected in dry-run mode to allow CI gating.
        return 3 if total_legacy > 0 else 0

    # Phase 2: Apply (with confirmation)
    decision = _confirm_apply(args, total_legacy)
    if decision == 1:
        # For JSON mode with --apply but zero legacy rows we still emit a minimal applied payload.
        if args.json:
            # Represent applied phase with zero updates but preserve table structure for consistency.
            zero_reports = [TableReport(r.table, r.scanned, legacy_naive=0, updated=0) for r in reports]
            empty_payload = _reports_to_dict("applied", zero_reports)
            empty_payload["dry_run"] = _reports_to_dict("dry_run", reports)
            print(json.dumps(empty_payload, indent=2))
        return 0
    if decision == 2:
        return 2

    update_reports = _apply_phase(args.db_path, args.json)
    if args.json:
        payload = _reports_to_dict("applied", update_reports)
        payload["dry_run"] = _reports_to_dict("dry_run", reports)
        print(json.dumps(payload, indent=2))
    else:
        _print_reports("Applied Updates", update_reports)
        print(
            f"TOTAL      |         | {sum(r.legacy_naive for r in update_reports):12} | {sum(r.updated for r in update_reports):7}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual script entry
    raise SystemExit(main())
