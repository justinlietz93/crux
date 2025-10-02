"""Utilities for parsing ``ollama list`` table output.

Purpose
    Convert human-readable CLI tables into normalized model metadata used by
    the Ollama provider.

External Dependencies
    * Standard library :mod:`re` for column segmentation.

Fallback Semantics
    Parsing helpers return empty collections on missing data and surface
    malformed inputs to callers without additional fallbacks.

Timeout Strategy
    Not applicable; functions execute synchronously without external I/O.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def split_table_columns(line: str) -> List[str]:
    """Split a table row by two-or-more spaces while preserving token groups.

    Parameters
    ----------
    line: str
        Raw line extracted from ``ollama list`` output.

    Returns
    -------
    List[str]
        Trimmed column fragments with empty segments removed.
    """

    return [column.strip() for column in re.split(r"\s{2,}", line.strip()) if column.strip()]


def parse_header_map(header_line: str) -> Tuple[bool, Dict[str, int]]:
    """Return header presence indicator and column index mapping.

    Parameters
    ----------
    header_line: str
        First non-empty line from the CLI output.

    Returns
    -------
    Tuple[bool, Dict[str, int]]
        ``(has_header, header_map)`` where ``header_map`` uses uppercase keys.
    """

    columns = split_table_columns(header_line)
    has_header = any(column.upper() == "NAME" for column in columns)
    header_map = {column.upper(): index for index, column in enumerate(columns)} if has_header else {}
    return has_header, header_map


def entry_from_columns(columns: List[str], header_map: Dict[str, int]) -> Dict[str, Any]:
    """Build a normalized entry from segmented columns and header metadata.

    Parameters
    ----------
    columns: List[str]
        Individual column values extracted from a table line.
    header_map: Dict[str, int]
        Optional header mapping derived from :func:`parse_header_map`.

    Returns
    -------
    Dict[str, Any]
        Mapping containing at minimum ``id`` and ``name`` keys with optional
        digest, size, and modified metadata when available.
    """

    if header_map and "NAME" in header_map and len(columns) > header_map["NAME"]:
        name = columns[header_map["NAME"]]
    else:
        name = columns[0]

    entry: Dict[str, Any] = {"id": name, "name": name}
    if header_map:
        if "ID" in header_map and len(columns) > header_map["ID"]:
            entry["id_digest"] = columns[header_map["ID"]]
        if "SIZE" in header_map and len(columns) > header_map["SIZE"]:
            entry["size"] = columns[header_map["SIZE"]]
        if "MODIFIED" in header_map and len(columns) > header_map["MODIFIED"]:
            entry["modified"] = columns[header_map["MODIFIED"]]
    return entry


def parse_ollama_list_table(output: str) -> List[Dict[str, Any]]:
    """Parse human-readable ``ollama list`` table output into model entries.

    Parameters
    ----------
    output: str
        Raw stdout returned from ``ollama list`` without ``--json``.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model entries suitable for persistence.
    """

    lines = [line.rstrip() for line in (output or "").splitlines() if line.strip()]
    if not lines:
        return []

    has_header, header_map = parse_header_map(lines[0])
    data_lines = lines[1:] if has_header else lines

    items: List[Dict[str, Any]] = []
    for line in data_lines:
        columns = split_table_columns(line)
        if not columns:
            continue
        items.append(entry_from_columns(columns, header_map))

    return items


__all__ = [
    "split_table_columns",
    "parse_header_map",
    "entry_from_columns",
    "parse_ollama_list_table",
]
