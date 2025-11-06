"""CLI action handlers and provider helpers.

Purpose
-------
Reusable helpers and subcommand handlers for the providers CLI, keeping the
main entrypoint file minimal per architecture rules (thin presentation layer).
This module has no top-level side effects and is safe to import in tests.

External Dependencies
---------------------
- Relies on provider adapter implementations (e.g., OpenRouter, OpenAI) that
    may use HTTP clients (such as ``httpx``) when executing real calls.

Timeout Strategy
----------------
- All blocking start phases of execution use ``get_timeout_config()`` and
    ``operation_timeout``; no hard-coded numeric timeouts are introduced.

Fallback & Error Semantics
--------------------------
- Dry-run paths avoid network I/O and only inspect environment and adapters.
- Execution paths emit normalized structured logs; errors are surfaced as JSON
    to stderr and non-zero return codes, without masking exception types in logs.

Docstring Policy
----------------
Public functions include comprehensive docstrings covering purpose, parameters,
return values, failure modes, and side effects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import import_module
from typing import Any, Dict, Optional

from ...base.logging import LogContext, get_logger, normalized_log_event
from ...base.models import ChatRequest, Message
from ...base.streaming import streaming_supported
from ...base.timeouts import get_timeout_config, operation_timeout
from ...config.env import get_env_var_candidates
from ...base.factory import ProviderFactory, UnknownProviderError
from ..helpers import set_env_for_provider


def get_api_key(adapter: Any) -> Optional[str]:
    """Return the adapter's API key if available, otherwise ``None``.

    Parameters
    ----------
    adapter: Any
        A provider adapter instance that may expose a private ``_api_key``
        attribute. Access is intentionally guarded and failure-safe.

    Returns
    -------
    Optional[str]
        The API key value when present; otherwise ``None``.

    Notes
    -----
    This helper centralizes attribute access, avoiding scattered ``getattr``
    calls or broad exception handling at call sites.
    """
    try:
        return adapter._api_key  # type: ignore[attr-defined]
    except Exception:
        return None


def resolve_provider_class(name: str):
    """Resolve a provider adapter class by canonical name.

    Parameters
    ----------
    name: str
        Provider key such as ``openai`` or ``openrouter``.

    Returns
    -------
    type | None
        The adapter class when known; otherwise ``None``.

    Failure Modes
    -------------
    - Unknown names yield ``None`` (no exception).
    - Import errors bubble up to aid debugging if the module path exists but
      fails during import (e.g., missing dependency).
    """
    mapping = {
        "openrouter": ("crux_providers.openrouter.client", "OpenRouterProvider"),
        "openai": ("crux_providers.openai.client", "OpenAIProvider"),
        "xai": ("crux_providers.xai.client", "XAIProvider"),
        "deepseek": ("crux_providers.deepseek.client", "DeepseekProvider"),
        "anthropic": ("crux_providers.anthropic.client", "AnthropicProvider"),
        "gemini": ("crux_providers.gemini.client", "GeminiProvider"),
        "ollama": ("crux_providers.ollama.client", "OllamaProvider"),
        "mock": ("crux_providers.mock.client", "MockProvider"),
    }
    item = mapping.get((name or "").lower().strip())
    if not item:
        return None
    mod = import_module(item[0])
    return getattr(mod, item[1], None)


# Backwards-compat alias for prior internal import sites
_resolve_provider_class = resolve_provider_class


def instantiate_adapter(provider: str) -> Optional[Any]:
    """Instantiate and return an adapter for a provider.

    Parameters
    ----------
    provider: str
        Canonical provider name.

    Returns
    -------
    Optional[Any]
        Adapter instance on success; ``None`` if the provider is unknown or
        if the adapter constructor raised an exception.
    """
    try:
        return ProviderFactory.create(provider)
    except UnknownProviderError:
        return None
    except Exception:
        return None


def adapter_default_model(adapter: Any) -> Optional[str]:
    """Return the adapter's default model name if available.

    Parameters
    ----------
    adapter: Any
        Provider adapter instance.

    Returns
    -------
    Optional[str]
        Default model identifier; ``None`` if the adapter doesn't expose one.
    """
    try:
        return adapter.default_model()  # type: ignore[call-arg]
    except Exception:
        return None


def streaming_capable(adapter: Any) -> bool:
    """Return True if streaming would be supported given the current API key.

    Parameters
    ----------
    adapter: Any
        Provider adapter instance.

    Returns
    -------
    bool
        ``True`` when the adapter supports streaming and an API key is present.

    Notes
    -----
    Uses ``streaming_supported`` with ``require_api_key=True`` to avoid
    accidental network usage when keys are missing.
    """
    return streaming_supported(
        object(), require_api_key=True, api_key_getter=lambda: get_api_key(adapter)
    )


def plan_run(*, provider: str, model: Optional[str], prompt: Optional[str], stream: bool) -> Dict[str, Any]:
    """Compute a dry-run execution plan for a provider call without I/O.

    Parameters
    ----------
    provider: str
        Canonical provider name (e.g., ``openrouter``).
    model: Optional[str]
        Optional model override; if ``None``, the adapter's default (if any)
        will be reported.
    prompt: Optional[str]
        Optional user prompt previewed in the plan output.
    stream: bool
        Whether streaming would be requested by the caller.

    Returns
    -------
    Dict[str, Any]
        JSON-serializable summary of the intended call (no network access).
    """
    # Ensure keys in .env or aliases are promoted before adapter instantiation
    set_env_for_provider(provider)
    adapter = instantiate_adapter(provider)
    has_adapter = adapter is not None
    default_model = adapter_default_model(adapter) if has_adapter else None
    return {
        "provider": provider,
        "model": model or default_model,
        "prompt_preview": (f"{prompt[:64]}…" if (prompt and len(prompt) > 64) else prompt),
        "stream_requested": stream,
        "adapter_available": has_adapter,
        "api_key_present": bool(get_api_key(adapter)) if has_adapter else False,
        "streaming_supported": streaming_capable(adapter) if has_adapter else False,
    }


def execute(provider: str, model: Optional[str], prompt: str, stream: bool) -> int:
    """Execute a simple provider call with standardized timeouts and logging.

    Parameters
    ----------
    provider: str
        Canonical provider name.
    model: Optional[str]
        Optional model override; falls back to adapter default.
    prompt: str
        User prompt text.
    stream: bool
        When ``True`` and supported, use streaming; otherwise standard call.

    Returns
    -------
    int
        ``0`` on success; non-zero on failure (errors printed as JSON to stderr).

    Failure Modes
    -------------
    - Missing API key: returns ``2`` with a JSON hint to stderr.
    - Unknown provider: returns ``2`` with an error to stderr.
    - Runtime error during call: returns ``1`` and logs a normalized error event.

    Side Effects
    ------------
    - Emits normalized structured log events for start/finalize/error.
    - May perform network I/O via provider adapters when executing.

    Timeout/Retry Notes
    -------------------
    - Blocking start phases are wrapped by ``operation_timeout`` configured via
      ``get_timeout_config()``. Centralized retry policy is not applied here.
    """
    # Auto-load .env / promote alias keys before resolving adapter
    set_env_for_provider(provider)
    adapter_cls = resolve_provider_class(provider)
    if adapter_cls is None:
        print(json.dumps({"error": f"unknown provider '{provider}'"}), file=sys.stderr)
        return 2

    env_candidates = list(get_env_var_candidates(provider))
    if not any(os.environ.get(name) for name in env_candidates):
        hint = {"error": f"missing API key for provider '{provider}'", "set_one_of_env": env_candidates}
        print(json.dumps(hint), file=sys.stderr)
        return 2

    adapter = adapter_cls()
    if not bool(get_api_key(adapter)):
        hint = {"error": f"missing API key for provider '{provider}'", "set_one_of_env": env_candidates}
        print(json.dumps(hint), file=sys.stderr)
        return 2

    try:
        mdl = model or adapter.default_model() or "auto"  # type: ignore[assignment]
    except Exception:
        mdl = model or "auto"

    logger = get_logger(f"providers.cli.{provider}")
    ctx = LogContext(provider=provider, model=mdl)
    req = ChatRequest(model=mdl, messages=[Message(role="user", content=prompt)])
    normalized_log_event(logger, "cli.start", ctx, phase="start", attempt=1, emitted=None, tokens=None)

    def _run_call() -> str:
        cfg = get_timeout_config()
        with operation_timeout(cfg.start_timeout_seconds):
            if stream and streaming_capable(adapter):
                parts: list[str] = []
                for ev in adapter.stream_chat(req):
                    if ev.delta:
                        parts.append(ev.delta)
                return "".join(parts)
            resp = adapter.chat(req)
            return resp.text or ""

    try:
        out = _run_call()
        print(out)
        normalized_log_event(
            logger, "cli.finalize", ctx, phase="finalize", attempt=None, emitted=bool(out), tokens=None
        )
        return 0
    except Exception as e:
        normalized_log_event(
            logger, "cli.error", ctx, phase="finalize", attempt=None, emitted=False, tokens=None, error=str(e)
        )
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    # interactive shell helpers moved to service/cli_shell.py


def handle_benchmark(args: argparse.Namespace, *, run_benchmark_fn) -> int:
    """Execute the ``benchmark`` subcommand.

    Parameters
    ----------
    args: argparse.Namespace
        Parsed CLI arguments containing provider, model, prompt, runs, warmups,
        stream, and output control flags.
    run_benchmark_fn: Callable
        Injection point for the benchmark implementation (improves testability).

    Returns
    -------
    int
        ``0`` on success; ``1`` if an exception is raised (printed as JSON).
    """
    try:
        result = run_benchmark_fn(
            provider=args.provider,
            model=args.model,
            prompt=args.prompt,
            runs=args.runs,
            warmups=args.warmups,
            stream=args.stream,
            capture_output=not bool(args.no_output),
        )
        print(json.dumps({k: v for k, v in result.items() if k in ("warmup", "measured")}))
        if not args.no_output and (sample := result.get("sample_output", "")):
            print("\n--- sample output ---\n" + sample)
        return 0
    except Exception as e:  # pragma: no cover
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def handle_smoke(args: argparse.Namespace) -> int:
    """Execute the ``smoke`` subcommand across multiple providers.

    Parameters
    ----------
    args: argparse.Namespace
        Parsed CLI arguments including ``providers``, ``prompt``, ``model``,
        ``stream``, and optional ``json`` summary flag.

    Returns
    -------
    int
        ``0`` when all providers succeed; ``1`` when any provider fails.
    """
    results = []
    for prov in args.providers:
        adapter_cls = resolve_provider_class(prov)
        status: Dict[str, Any] = {
            "provider": prov,
            "adapter_available": bool(adapter_cls),
            "ok": False,
            "error": None,
            "stream": bool(args.stream),
        }
        if adapter_cls is None:
            status["error"] = "unknown provider"
            results.append(status)
            print(f"[{prov}] skip: unknown provider")
            continue
        try:
            set_env_for_provider(prov)
            rc = execute(prov, args.model, args.prompt, bool(args.stream))
            status["ok"] = (rc == 0)
            status["error"] = (None if rc == 0 else f"exit={rc}")
            print(f"[{prov}] {'ok' if rc == 0 else 'fail'}")
        except Exception as e:  # pragma: no cover
            status["ok"] = False
            status["error"] = str(e)
            print(f"[{prov}] error: {e}")
        results.append(status)

    if getattr(args, "json", False):
        print(json.dumps({"results": results}))
    return 0 if all(r.get("ok") for r in results) else 1


def handle_run(args: argparse.Namespace) -> int:
    """Execute the default ``run`` subcommand (inspect or execute).

    Parameters
    ----------
    args: argparse.Namespace
        Parsed CLI arguments for a single provider call.

    Returns
    -------
    int
        ``0`` for dry-run plan emission or successful execution; non-zero on
        validation or execution error.
    """
    if not args.execute:
        print(json.dumps(plan_run(provider=args.provider, model=args.model, prompt=args.prompt, stream=args.stream)))
        return 0
    if not args.prompt:
        print(json.dumps({"error": "--prompt is required with --execute"}), file=sys.stderr)
        return 2
    return execute(args.provider, args.model, args.prompt, args.stream)
