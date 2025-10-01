"""Message extraction helpers shared across providers.

This module provides small utilities that normalize chat message content
for downstream provider adapters. Helpers here must be side-effect free
and operate on provider-agnostic DTOs only.
"""
from __future__ import annotations

from typing import Optional, List, Tuple
from ...utils.input_size_guard import (
    is_guard_enabled,
    get_max_input_chars,
    condense_text_to_limit,
)
from ...base.models import Message

# Cache guard configuration at import time.
# Rationale: Some tests reload this module after temporarily setting
# environment variables to assert behavior. Reading the configuration once
# ensures deterministic behavior until the next reload, avoiding surprising
# mid-execution changes based on ambient environment.
_GUARD_ENABLED = is_guard_enabled()
_MAX_INPUT_CHARS = get_max_input_chars()

def extract_system_and_user(messages: List[Message]) -> Tuple[Optional[str], str]:
    """Extract the first system message and a sanitized concatenation of user text.

    Summary
    - Returns a tuple ``(system_text, users_joined)`` where ``system_text`` is the
      content of the first system message (if present) and ``users_joined`` is a
      newline-delimited string built from user messages.

    Sanitization rules for user content
    - Structured message content is flattened using ``Message.text_or_joined()``.
    - The resulting text is split on newlines; each line is ``strip()``-ed.
    - Empty/whitespace-only lines are dropped before the final join.

    Notes
    - Non-``Message`` items are ignored.
    - Assistant/tool roles are currently ignored (subject to future expansion).

    Parameters
    - messages: List of ``Message`` DTOs (string or structured content).

    Returns
    - Tuple[Optional[str], str]: ``(first_system_message_or_None, users_text)``.

    Failure modes
    - No exceptions are raised in normal operation; malformed items are skipped.
    - When the optional input size guard is enabled via environment variables, a
      ``ValueError`` may be raised if the concatenated user text exceeds the configured
    character limit. See ``crux_providers.utils.input_size_guard`` for configuration.
    - Function is otherwise pure (no I/O, no side effects).
    """
    system_message: Optional[str] = None
    user_segments: List[str] = []
    for m in messages:
        if not isinstance(m, Message):
            continue
        if m.role == "system" and system_message is None:
            system_message = m.text_or_joined()
        elif m.role == "user":
            # Flatten, trim, and drop empty/whitespace-only segments.
            text = m.text_or_joined()
            for seg in text.split("\n"):
                if trimmed := seg.strip():
                    user_segments.append(trimmed)
    users_joined = "\n".join(user_segments)
    # Optional condensation when enabled by ENV flags and a positive max.
    if users_joined and _GUARD_ENABLED:
        eff_max = _MAX_INPUT_CHARS
        if eff_max > 0 and len(users_joined) > eff_max:
            users_joined = condense_text_to_limit(users_joined, eff_max)
    return system_message, users_joined

__all__ = ["extract_system_and_user"]
