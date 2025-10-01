"""Unit tests for Ollama CLI table parsing.

Validates robust parsing of ``ollama list`` human-readable output across
spacing variations and with/without headers.
"""

from __future__ import annotations

from crux_providers.ollama.get_ollama_models import _parse_ollama_list_table


def test_parse_with_header_multiple_spaces() -> None:
    """Parser handles standard header and variable spacing within columns."""
    sample = (
        "NAME            ID                         SIZE    MODIFIED\n"
        "llama3.1:8b     sha256:abc123               4.1 GB  2 weeks ago\n"
        "qwen2.5:14b     sha256:def456               7.8 GB  3 days ago\n"
    )

    items = _parse_ollama_list_table(sample)

    assert len(items) == 2
    assert items[0]["name"] == "llama3.1:8b"
    assert items[0]["id"] == "llama3.1:8b"
    assert items[0]["id_digest"] == "sha256:abc123"
    assert items[0]["size"] == "4.1 GB"
    assert items[0]["modified"] == "2 weeks ago"

    assert items[1]["name"] == "qwen2.5:14b"
    assert items[1]["id_digest"] == "sha256:def456"
    assert items[1]["size"] == "7.8 GB"
    assert items[1]["modified"] == "3 days ago"


def test_parse_without_header_assumes_first_column_name() -> None:
    """Parser tolerates outputs without a header by using first column as name."""
    sample = (
        "llama3.1:8b     sha256:abc123               4.1 GB  2 weeks ago\n"
        "qwen2.5:14b     sha256:def456               7.8 GB  3 days ago\n"
    )

    items = _parse_ollama_list_table(sample)
    assert len(items) == 2
    assert items[0]["name"] == "llama3.1:8b"
    assert items[0]["id"] == "llama3.1:8b"
    # Without header, extra fields may be absent; ensure graceful presence of essentials
    assert set(items[0].keys()) >= {"id", "name"}
