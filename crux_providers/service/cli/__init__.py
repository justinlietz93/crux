"""Providers Debugging CLI (package entrypoint).

This package wires argument parsing to action handlers kept in small, focused
modules to satisfy the 500 LOC rule and improve testability. It performs no
provider logic directly.

Public API re-exports:
- ``main``: CLI entrypoint callable
- ``_plan_run``: Dry-run planner used by tests
"""

from __future__ import annotations

import sys
from typing import Optional

from .cli_actions import handle_benchmark, handle_run
from .cli_actions import handle_smoke  # wired at call time to avoid circularity
from .cli_actions import plan_run as _plan_run  # backward-compat for tests
from .cli_parser import build_parser
from .cli_shell import handle_shell


def main(argv: Optional[list[str]] = None) -> int:
	"""CLI entrypoint.

	Parameters
	----------
	argv: Optional[list[str]]
		Argument vector; when ``None`` uses ``sys.argv[1:]``.

	Returns
	-------
	int
		Process exit code (0 success, non-zero on error).
	"""
	p = build_parser()
	# Parse provided argv or fall back to real command-line args
	# Prepare argv and inject default subcommand "run" when omitted.
	argv_list = list(sys.argv[1:] if argv is None else argv)
	if not argv_list or (
		argv_list[0].startswith("-") or argv_list[0] not in {"run", "benchmark", "smoke", "shell"}
	):
		argv_list = ["run"] + argv_list
	args = p.parse_args(argv_list)

	if args.cmd == "benchmark":
		# Local import to avoid importing benchmark at module import time
		from ..benchmark import run_benchmark as _rb

		return handle_benchmark(args, run_benchmark_fn=_rb)
	if args.cmd == "smoke":
		return handle_smoke(args)
	return handle_shell(args) if args.cmd == "shell" else handle_run(args)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(main())
