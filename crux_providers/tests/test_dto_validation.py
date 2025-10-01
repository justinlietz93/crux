"""Tests for crux_providers.base.dto_validation DTOs.

Covers happy paths and key edge cases for message/content validation and
parameter bounds.
"""

from __future__ import annotations

import pytest

from crux_providers.base.dto import (
    ChatRequestDTO,
    ContentPartDTO,
    MessageDTO,
)


def test_chat_request_happy_path_with_text_content():
    req = ChatRequestDTO(
        model="gpt-4o-mini",
        messages=[
            MessageDTO(role="system", content="You are helpful."),
            MessageDTO(role="user", content="Hello"),
        ],
        max_tokens=128,
        temperature=0.7,
    )
    assert req.model == "gpt-4o-mini"
    assert len(req.messages) == 2


def test_message_user_requires_non_empty_content_parts():
    with pytest.raises(Exception):
        MessageDTO(role="user", content=[ContentPartDTO(type="text", text=" ")])

    ok = MessageDTO(role="user", content=[ContentPartDTO(type="text", text="hi")])
    assert ok.content[0].text == "hi"


def test_message_rejects_empty_string():
    with pytest.raises(Exception):
        MessageDTO(role="assistant", content=" ")


def test_message_rejects_empty_parts_list():
    with pytest.raises(Exception):
        MessageDTO(role="assistant", content=[])


def test_bounds_validation():
    # max_tokens must be > 0
    with pytest.raises(Exception):
        ChatRequestDTO(
            model="x",
            messages=[MessageDTO(role="system", content="start")],
            max_tokens=0,
        )

    # temperature must be within [0,2]
    with pytest.raises(Exception):
        ChatRequestDTO(
            model="x",
            messages=[MessageDTO(role="system", content="start")],
            temperature=2.5,
        )


def test_first_message_role_constraint():
    with pytest.raises(Exception):
        ChatRequestDTO(
            model="x",
            messages=[
                MessageDTO(role="assistant", content="hi"),
                MessageDTO(role="user", content="hello"),
            ],
        )
