"""Unit tests for `crux_providers.base.utils.messages` helpers.

Covers handling of system/user messages, structured content parts, and
ignoring non-`Message` instances while concatenating user segments.
"""
from __future__ import annotations

from crux_providers.base.models import Message, ContentPart
from crux_providers.base.utils.messages import extract_system_and_user


def test_extract_system_and_user_with_text_and_structured():
    """It returns first system text and newline-joined user segments.

    Structured content parts should be joined by their text or compact tag.
    Non-Message items are ignored.
    """
    msgs = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hello"),
        # Structured parts
        Message(
            role="user",
            content=[
                ContentPart(type="text", text="Part A"),
                ContentPart(type="json", data={"k": "v"}),
            ],
        ),
        {"role": "assistant", "content": "ignored non-Message"},  # ignored
    ]

    sys_msg, users = extract_system_and_user(msgs)

    assert sys_msg == "You are helpful."
    # Second user message expands to two lines (text + [json])
    assert users.split("\n") == ["Hello", "Part A", "[json]"]


def test_extract_system_and_user_without_system_or_empty_segments():
    """When no system is present return None; empty user segments are filtered."""
    msgs = [
        Message(role="user", content=""),
        Message(role="user", content=[ContentPart(type="text", text=None)]),
        Message(role="user", content="Hi"),
    ]
    sys_msg, users = extract_system_and_user(msgs)
    assert sys_msg is None
    # Structured text part without explicit text becomes a compact tag line
    assert users == "[text]\nHi"
