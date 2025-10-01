"""Input size guard utilities.

Purpose
-------
Provide an environment-configurable guard to protect against accidentally
sending excessively large prompts/inputs to providers.

This module is framework-agnostic and lives under ``crux_providers/utils`` to
respect the layered architecture. It contains no side-effects on import and
reads environment variables only when functions are invoked.

Environment Variables
---------------------
- ``PROVIDERS_MAX_INPUT_ENABLED``: If set to a truthy value ("1", "true",
    case-insensitive), the guard is active. Default: enabled.
- ``PROVIDERS_MAX_INPUT_CHARS``: Maximum allowed character length when enabled.
    Default: 0 (interpreted as no-op even when enabled).

Contract
--------
Functions raise ``ValueError`` when the guard is enabled and the input exceeds
the configured limit. Callers may catch the exception and choose to truncate
or condense instead; this module provides a deterministic helper
(:func:`condense_text_to_limit`) for lossy condensation when desired.

Examples
--------
>>> enforce_max_input("hello")  # no-op when disabled
>>> enforce_max_input("x" * 10, enabled=True, max_chars=5)
Traceback (most recent call last):
    ...
ValueError: input exceeds configured maximum (len=10 > max=5)
"""

from __future__ import annotations

import os
from typing import Optional, Callable

# Importing models from the base package is acceptable for utilities living
# inside crux_providers/ per layered architecture (shared DTOs).
from crux_providers.base.models import ChatRequest, Message, ContentPart


def _str_to_bool(val: Optional[str]) -> bool:
    """Return True if the string value looks truthy.

    Accepted truthy forms: "1", "true", "yes", "on" (case-insensitive).
    """
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def is_guard_enabled(default: bool = True) -> bool:
    """Determine if the max-input guard is enabled from the environment.

    Parameters
    ----------
    default: bool
        Fallback when the environment variable is unset.

    Returns
    -------
    bool
        True when the guard is active.
    """
    return _str_to_bool(os.getenv("PROVIDERS_MAX_INPUT_ENABLED")) or default


def get_max_input_chars(default: int = 0) -> int:
    """Return the configured max input size in characters.

    Non-positive values are treated as disabled (no-op) by callers.

    Parameters
    ----------
    default: int
        Fallback value when env is unset or invalid.

    Returns
    -------
    int
        Maximum allowed character count.
    """
    raw = os.getenv("PROVIDERS_MAX_INPUT_CHARS")
    if not raw:
        return max(0, default)
    try:
        return max(0, int(raw))
    except ValueError:
        return max(0, default)


def enforce_max_input(value: str, *, enabled: Optional[bool] = None, max_chars: Optional[int] = None) -> None:
    """Validate that ``value`` does not exceed the configured maximum.

    This function does not modify the input. It raises ``ValueError`` when the
    guard is active and the value length exceeds the maximum threshold.

    Parameters
    ----------
    value: str
        The input string (prompt) to validate.
    enabled: Optional[bool]
        Optional override for enabling the guard. If ``None``, consults
        the environment via :func:`is_guard_enabled`.
    max_chars: Optional[int]
        Optional override for maximum characters. If ``None``, reads from
        :func:`get_max_input_chars`.

    Raises
    ------
    ValueError
        If the guard is enabled and the input length exceeds the limit.
    """
    eff_enabled = is_guard_enabled() if enabled is None else bool(enabled)
    if not eff_enabled:
        return
    eff_max = get_max_input_chars() if max_chars is None else max_chars
    if eff_max <= 0:
        return
    length = len(value or "")
    if length > eff_max:
        raise ValueError(f"input exceeds configured maximum (len={length} > max={eff_max})")


def _default_summarizer(text: str, target: int) -> str:
    """Return a deterministic, lossy summary bounded by ``target`` characters.

    Strategy
    - For very small targets (<= 3), return a hard truncation to ``target``.
    - Otherwise, keep a head and tail slice with a single ellipsis in between,
      roughly preserving both ends of the content: ``head + '…' + tail``.

    Notes
    - This function is pure and performs no I/O.
    - It never raises; on unexpected inputs it falls back to a safe truncation.

    Parameters
    ----------
    text: str
        Source text to summarize.
    target: int
        Maximum length of the summary (non-negative).

    Returns
    -------
    str
        A summarized string not exceeding ``target`` characters.
    """
    if target <= 0:
        return ""
    if len(text) <= target:
        return text
    if target <= 3:
        return text[:target]
    # Reserve 1 char for the ellipsis
    keep = target - 1
    # Split head/tail roughly evenly; bias head by one when odd
    head_len = (keep + 1) // 2
    tail_len = keep - head_len
    try:
        return f"{text[:head_len]}…{text[-tail_len:] if tail_len > 0 else ''}"
    except Exception:
        return text[:target]


def _condense_short_circuit(value: str, max_chars: int) -> Optional[str]:
    """Return early condensed result when trivial cases apply.

    Parameters
    ----------
    value: str
        Source string.
    max_chars: int
        Maximum allowed characters; non-positive returns empty string.

    Returns
    -------
    Optional[str]
        ``None`` when further processing is required; otherwise the
        final condensed string.
    """
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return None


def _calc_initial_target(chunk_chars: int) -> int:
    """Compute the initial per-chunk target for summarization.

    Uses roughly 50% reduction of the chunk size while preserving a minimum
    signal of 16 characters per chunk.
    """
    return max(16, chunk_chars // 2)


def _summarize_chunks(text: str, chunk_chars: int, target: int, summarize: Callable[[str, int], str]) -> str:
    """Summarize ``text`` by chunking and applying ``summarize`` per chunk."""
    summaries = []
    for i in range(0, len(text), chunk_chars):
        chunk = text[i : i + chunk_chars]
        summaries.append(summarize(chunk, target))
    return "\n".join(summaries)


def _tighten_target_if_needed(current_len: int, chunk_chars: int, target: int) -> int:
    """Tighten the per-chunk target when the text has significantly shrunk."""
    if current_len < (chunk_chars // 2):
        return max(16, target // 2)
    return target


def _final_truncate(text: str, max_chars: int) -> str:
    """Enforce the final bound using the deterministic summarizer."""
    return _default_summarizer(text, max_chars)


def condense_text_to_limit(
    value: str,
    max_chars: int,
    *,
    chunk_chars: int = 4000,
    summarize: Optional[Callable[[str, int], str]] = None,
    max_iterations: int = 10,
) -> str:
    """Condense ``value`` until it fits within ``max_chars``.

    See module docstring for algorithm overview. This function is intentionally
    concise and delegates work to small helpers to keep it maintainable and
    within the LOC threshold without sacrificing clarity or behavior.
    """
    if (res := _condense_short_circuit(value, max_chars)) is not None:
        return res
    summarize_fn = summarize or _default_summarizer
    current = value
    per_chunk_target = _calc_initial_target(chunk_chars)
    iterations = 0
    while len(current) > max_chars and iterations < max_iterations:
        iterations += 1
        current = _summarize_chunks(current, chunk_chars, per_chunk_target, summarize_fn)
        per_chunk_target = _tighten_target_if_needed(len(current), chunk_chars, per_chunk_target)
    if len(current) > max_chars:
        return _final_truncate(current, max_chars)
    return current


def _content_text_length(msg: Message) -> int:
    """Compute visible text length for a :class:`Message`.

    This helper accounts for multipart content by summing the length of the
    ``text`` field for parts of type ``"text"`` (case-insensitive). Non-text
    parts are ignored for the purposes of size guarding.

    Parameters
    ----------
    msg: Message
        The message whose textual content length should be measured.

    Returns
    -------
    int
        Total number of characters considered for size checks.
    """
    content = msg.content
    if isinstance(content, list):
        # Sum lengths for explicit ContentPart instances with text type
        part_len = sum(
            len(p.text or "")
            for p in content
            if isinstance(p, ContentPart) and str(p.type).lower() == "text"
        )
        # Allow dict-shaped parts in edge cases (e.g., tests feeding raw dicts)
        dict_len = sum(
            len(str(p.get("text", "")))
            for p in content
            if isinstance(p, dict) and str(p.get("type", "text")).lower() == "text"
        )
        return part_len + dict_len
    # Simple string content
    return len(str(content or ""))


def measure_request_chars(req: ChatRequest) -> int:
    """Measure the total visible text length of a :class:`ChatRequest`.

    Sums the per-message visible text length computed by
    :func:`_content_text_length`. System/tool messages count as well; the guard
    is concerned with total request payload size rather than role.

    Parameters
    ----------
    req: ChatRequest
        The chat request to measure.

    Returns
    -------
    int
        Total number of characters across all message content.
    """
    return sum(_content_text_length(m) for m in req.messages)


def enforce_request_size(
    req: ChatRequest,
    *,
    enabled: Optional[bool] = None,
    max_chars: Optional[int] = None,
) -> None:
    """Validate that the aggregate request size does not exceed the limit.

    This function measures the total visible text content of the provided
    :class:`ChatRequest` and applies the same environment-configurable policy
    as :func:`enforce_max_input`. It does not mutate the request.

    Parameters
    ----------
    req: ChatRequest
        The request whose content should be validated.
    enabled: Optional[bool]
        Optional override to enable/disable the guard (default: consult env).
    max_chars: Optional[int]
        Optional override for maximum characters (default: consult env).

    Raises
    ------
    ValueError
        If the guard is active and the aggregate character count exceeds the
        configured maximum.
    """
    eff_enabled = is_guard_enabled() if enabled is None else bool(enabled)
    if not eff_enabled:
        return
    eff_max = get_max_input_chars() if max_chars is None else int(max_chars)
    if eff_max <= 0:
        return
    length = measure_request_chars(req)
    if length > eff_max:
        raise ValueError(f"input exceeds configured maximum (len={length} > max={eff_max})")


__all__ = [
    "is_guard_enabled",
    "get_max_input_chars",
    "enforce_max_input",
    "measure_request_chars",
    "enforce_request_size",
    "condense_text_to_limit",
]
