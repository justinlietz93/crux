"""Streaming metrics data structures.

Isolated within the streaming package to keep orchestration code small and cohesive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple


@dataclass
class StreamMetrics:
    """Collected streaming metrics for a single provider invocation.

    See original module docstring for detailed field semantics.
    """

    emitted: int = 0
    time_to_first_token_ms: Optional[float] = None
    total_duration_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens: Optional[Dict[str, Any]] = None


def build_token_usage(prompt: Optional[int], completion: Optional[int], total: Optional[int] = None) -> Dict[str, Optional[int]]:
    """Return a canonical token usage mapping."""
    derived_total = total
    if derived_total is None and (prompt is not None and completion is not None):
        derived_total = prompt + completion
    return {"prompt": prompt, "completion": completion, "total": derived_total}


def apply_token_usage(metrics: StreamMetrics, *, prompt: Optional[int], completion: Optional[int], total: Optional[int] = None) -> None:
    """Populate token usage fields on a :class:`StreamMetrics` instance."""
    metrics.prompt_tokens = prompt
    metrics.completion_tokens = completion
    metrics.total_tokens = total if total is not None else (
        (prompt + completion) if (prompt is not None and completion is not None) else None
    )
    metrics.tokens = build_token_usage(metrics.prompt_tokens, metrics.completion_tokens, metrics.total_tokens)


def validate_token_usage(
    metrics: StreamMetrics,
    *,
    raise_on_error: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Validate token usage fields for internal consistency."""

    def _fail(reason: str) -> Tuple[bool, Optional[str]]:
        if raise_on_error:
            raise ValueError(f"token usage invalid: {reason}")
        return False, reason

    for name, value in (
        ("prompt_tokens", metrics.prompt_tokens),
        ("completion_tokens", metrics.completion_tokens),
        ("total_tokens", metrics.total_tokens),
    ):
        if value is not None and value < 0:
            return _fail(f"{name} negative: {value}")

    if (
        metrics.prompt_tokens is not None
        and metrics.completion_tokens is not None
        and metrics.total_tokens is not None
    ) and metrics.prompt_tokens + metrics.completion_tokens != metrics.total_tokens:
        return _fail("total_tokens mismatch: expected prompt+completion == total")

    if metrics.tokens is not None:
        required = {"prompt", "completion", "total"}
        if set(metrics.tokens.keys()) != required:
            return _fail(f"tokens mapping keys mismatch: {sorted(metrics.tokens.keys())}")

    return True, None


__all__ = [
    "StreamMetrics",
    "apply_token_usage",
    "build_token_usage",
    "validate_token_usage",
]
