"""
Batch refresh utility for provider model registries (canonical location).
CLI Examples:
    python -m crux_providers.utils.refresh_all_models
    python -m crux_providers.utils.refresh_all_models --only openai,anthropic --parallel 3
    python -m crux_providers.utils.refresh_all_models --json --fail-on-error
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
from dataclasses import asdict, dataclass
from importlib import import_module
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional

from ..config.defaults import (
    PROVIDER_REFRESH_DEFAULT_PARALLEL,
    PROVIDER_REFRESH_DEFAULT_PROVIDERS,
)

FETCHER_NAME_TEMPLATE = "crux_providers.{provider}.get_{provider}_models"
ENTRYPOINT_CANDIDATES = [
    "run",
    "get_models",
    "fetch_models",
    "update_models",
    "refresh_models",
    "main",
]

@dataclass
class ProviderRefreshResult:
    """Represents the result of refreshing a provider's model registry.

    Captures provider name, success status, count of models, duration, and any error encountered.
    """

    provider: str
    ok: bool
    count: Optional[int]
    duration_ms: float
    error: Optional[str] = None
    fetched_via: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary for serialization.

        Returns:
            A dictionary representation of the refresh result.
        """
        return asdict(self)


def _select_entrypoint(mod) -> Callable[[], Any]:
    """Select the entrypoint function from a module for refreshing models.

    Iterates through candidate function names and returns the first callable found.

    Args:
        mod: The imported module to search for an entrypoint.

    Returns:
        The selected entrypoint function.

    Raises:
        AttributeError: If no valid entrypoint is found in the module.
    """
    for name in ENTRYPOINT_CANDIDATES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    raise AttributeError("No valid entrypoint found in module")


def refresh_provider(provider: str) -> ProviderRefreshResult:
    """Refresh the model registry for a single provider.

    Imports the provider's fetcher module, invokes its entrypoint, and returns the result with timing and error info.

    Args:
        provider: The provider name to refresh.

    Returns:
        A ProviderRefreshResult containing the outcome, count, duration, and any error.
    """
    t0 = perf_counter()
    try:
        module_name = FETCHER_NAME_TEMPLATE.format(provider=provider)
        mod = import_module(module_name)
        fn = _select_entrypoint(mod)
        data = fn()
        count = None
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict):
            count = 1
        return ProviderRefreshResult(
            provider=provider,
            ok=True,
            count=count,
            duration_ms=(perf_counter() - t0) * 1000.0,
        )
    except Exception as e:  # noqa: BLE001
        return ProviderRefreshResult(
            provider=provider,
            ok=False,
            count=None,
            duration_ms=(perf_counter() - t0) * 1000.0,
            error=str(e)[:300],
        )


def refresh_all(providers: List[str], parallel: int = PROVIDER_REFRESH_DEFAULT_PARALLEL) -> List[ProviderRefreshResult]:
    """Refresh the model registries for all specified providers.

    Runs refresh operations in parallel if requested, returning results in input order.

    Args:
        providers: List of provider names to refresh.
        parallel: Number of parallel threads to use.

    Returns:
        A list of ProviderRefreshResult objects, one per provider.
    """
    if parallel <= 1:
        return [refresh_provider(p) for p in providers]
    results: List[ProviderRefreshResult] = []
    with cf.ThreadPoolExecutor(max_workers=parallel) as executor:
        future_map = {executor.submit(refresh_provider, p): p for p in providers}
        results.extend(fut.result() for fut in cf.as_completed(future_map))
    ordered: Dict[str, ProviderRefreshResult] = {r.provider: r for r in results}
    return [ordered[p] for p in providers]


def _parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command-line arguments for the batch refresh utility.

    Sets up the argument parser and returns the parsed arguments namespace.

    Args:
        argv: List of command-line arguments.

    Returns:
        An argparse.Namespace containing parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Batch refresh provider model registries"
    )
    parser.add_argument(
        "--only", help="Comma-separated subset of providers", default=None
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=PROVIDER_REFRESH_DEFAULT_PARALLEL,
        help=f"Parallel threads (default {PROVIDER_REFRESH_DEFAULT_PARALLEL})",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON report only")
    parser.add_argument(
        "--fail-on-error", action="store_true", help="Exit 1 if any provider fails"
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the batch provider model refresh utility.

    Parses arguments, refreshes all specified providers, prints results, and returns an exit code.

    Args:
        argv: Optional list of command-line arguments.

    Returns:
        Exit code: 0 if all providers succeeded, 1 if any failed and --fail-on-error is set.
    """
    args = _parse_args(argv or [])
    providers = PROVIDER_REFRESH_DEFAULT_PROVIDERS
    if args.only:
        providers = [p.strip() for p in args.only.split(",") if p.strip()]
    results = refresh_all(providers, parallel=max(1, args.parallel))
    report = {
        "summary": {
            "total": len(results),
            "ok": sum(bool(r.ok) for r in results),
            "failed": sum(not r.ok for r in results),
        },
        "results": [r.to_dict() for r in results],
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Provider Model Refresh Results:\n")
        for r in results:
            status = "OK" if r.ok else "FAIL"
            print(
                f"- {r.provider:10} {status:4} count={r.count!s:>4} time={r.duration_ms:7.1f}ms"
                + (f" err={r.error}" if r.error else "")
            )
        print(
            "\nSummary: {ok}/{total} succeeded, {failed} failed".format(
                **report["summary"]
            )
        )
    return 1 if args.fail_on_error and any(not r.ok for r in results) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
