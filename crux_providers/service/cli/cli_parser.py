"""CLI parser construction for providers-cli.

This module wires subparsers but contains no execution logic. Subcommand
handlers live in ``cli_actions`` to keep files small and testable.
"""

from __future__ import annotations

import argparse

# Back-compat export used by unit tests; parser module exposes plan helper
from .cli_actions import plan_run as _plan_run  # noqa: F401 (re-export for tests)


def _str2bool(v: str | None) -> bool:
    """Best-effort conversion of common truthy/falsey strings to bool.

    Parameters
    ----------
    v: str | None
        Incoming string value (e.g., "true", "false", "1", "0"). When ``None``
        and used via argparse with ``const=True``, this returns ``True``.

    Returns
    -------
    bool
        Parsed boolean value with a permissive mapping for typical CLI inputs.
    """
    if v is None:
        return True
    val = v.strip().lower()
    if val in {"1", "t", "true", "y", "yes", "on"}:
        return True
    return False if val in {"0", "f", "false", "n", "no", "off"} else bool(val)


def add_stream_flags(parser: argparse.ArgumentParser) -> None:
        """Attach ``--stream``/``--no-stream`` flags to a parser.

        Notes
        -----
        - ``--stream`` accepts an optional boolean (e.g., ``--stream``, ``--stream true``,
            ``--stream false``). Without a value it defaults to ``True``.
        - ``--no-stream`` is an explicit negation alias equivalent to ``--stream false``.
        """
        grp = parser.add_mutually_exclusive_group()
        grp.add_argument("--stream", nargs="?", const=True, type=_str2bool, default=False)
        grp.add_argument("--no-stream", dest="stream", action="store_false")


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level CLI parser and subcommands.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser with ``run``, ``benchmark``, and ``smoke`` subcommands.

    Design
    ------
    This function performs no side effects and wires only argument shapes. The
    subcommand handlers are implemented in ``cli_actions`` to keep the
    presentation layer thin and testable. No I/O or network calls occur here.
    """
    p = argparse.ArgumentParser(
        prog="providers-cli", description="Providers debugging CLI (safe by default: dry-run)"
    )
    sub = p.add_subparsers(dest="cmd")

    # run
    p_run = sub.add_parser("run", help="Inspect or execute a simple prompt (default)")
    p_run.add_argument("--provider", default="openrouter")
    p_run.add_argument("--model", default=None)
    p_run.add_argument("--prompt", default=None)
    add_stream_flags(p_run)
    p_run.add_argument("--execute", action="store_true")
    p_run.add_argument("--json", action="store_true")

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Run latency benchmark against a provider")
    p_bench.add_argument("--provider", default="openrouter")
    p_bench.add_argument("--model", default=None)
    p_bench.add_argument("--prompt", required=True)
    p_bench.add_argument("--runs", type=int, default=10)
    p_bench.add_argument("--warmups", type=int, default=2)
    add_stream_flags(p_bench)
    p_bench.add_argument("--no-output", action="store_true")

    # smoke (handler wired in cli.py to avoid circular import)
    p_smoke = sub.add_parser(
        "smoke",
        help="Run a simple conversation against multiple providers to validate basic connectivity",
    )
    p_smoke.add_argument(
        "--providers",
        nargs="+",
        default=["openai", "openrouter", "xai", "deepseek", "anthropic", "gemini"],
    )
    p_smoke.add_argument("--prompt", required=True)
    p_smoke.add_argument("--model", default=None)
    add_stream_flags(p_smoke)
    p_smoke.add_argument("--json", action="store_true")

    # shell (interactive REPL for headless usage)
    p_shell = sub.add_parser(
        "shell",
        help="Interactive headless shell to explore providers, models, and run chats",
    )
    p_shell.add_argument("--provider", default="openrouter")
    p_shell.add_argument("--model", default=None)
    add_stream_flags(p_shell)
    p_shell.add_argument("--live", action="store_true", help="Print tokens live when streaming")
    # In the shell, treat omitted flags as None so we can fall back to persisted settings
    p_shell.set_defaults(stream=None, live=None)

    return p
