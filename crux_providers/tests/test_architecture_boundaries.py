"""Architecture boundary guardrails for inner layers.

This suite enforces that provider-specific names and imports do not leak into
inner layers (e.g., ``crux_providers/base``). It is intentionally conservative
and path-based to catch drift early while allowing a transitional whitelist.

Policy alignment:
- Inner layers must be provider-agnostic. No provider names (e.g., "openai",
  "anthropic", "gemini", "openrouter", etc.) should appear in file paths or
  code within ``crux_providers/base``.
- Any short-term exceptions must be clearly whitelisted with a revisit date
  and a comment using the "deviation" format.

Note: During migration, this test will xfail when violations are detected.
Once cleanup is complete, switch xfail to assert to hard-enforce the boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Root of the repository is two levels up from this file
REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "crux_providers" / "base"


def _provider_regex() -> re.Pattern[str]:
    """Return a compiled regex to match provider names.

    Includes common providers we support or may support. Keep this list synced
    with the architecture upgrade doc and governance rules.
    """

    providers = [
        "openai",
        "anthropic",
        "claude",
        "gemini",
        "openrouter",
        "gpt",
        "ollama",
        "deepseek",
        "xai",
        "mistral",
        "cohere",
    ]
    # word-ish boundary to avoid overshooting unrelated substrings
    escaped = [re.escape(p) for p in providers]
    pattern = r"(?:^|[^a-z0-9_])(?:" + "|".join(escaped) + r")(?:[^a-z0-9_]|$)"
    return re.compile(pattern, re.IGNORECASE)


def _iter_py_files(root: Path) -> list[Path]:
    """Yield all Python files under ``root``.

    Skips common noise directories like ``__pycache__``.
    """

    files: list[Path] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        files.append(p)
    return files


def _is_transitional_allowed(path: Path) -> bool:
    """Return True if the path falls under a transitional exception.

    Deviation handling:
    - deviation: provider-bleed-cleanup reason=openai_style_parts under base
      revisit=2025-10-15
    """

    transitional_subpaths = [
        # Transitional module slated for removal/relocation
        Path("crux_providers/base/openai_style_parts"),
    ]
    as_str = str(path)
    return any(as_str.startswith(str((REPO_ROOT / sub).resolve())) for sub in transitional_subpaths)


def test_no_provider_names_in_base_paths():
    """Detect provider-name substrings in file paths under ``base/``.

    What this test proves:
    - Inner-layer modules are named generically (no provider labels).
    - Prevents accretion of provider coupling in the base layer.
    """

    rx = _provider_regex()
    violations: list[str] = []
    for py in _iter_py_files(BASE_DIR):
        # Skip known transitional exceptions
        if _is_transitional_allowed(py):
            continue
        if rx.search(str(py)):
            violations.append(f"path contains provider token: {py}")

    if violations:
        pytest.xfail(
            "provider-name tokens found in base/ paths — transitional xfail until cleanup: "
            + "; ".join(violations)
        )


def test_no_provider_mentions_in_base_file_contents():
    """Detect provider-name strings/imports inside base-layer Python files.

    What this test proves:
    - No provider-specific imports or literals are present in base-layer code.
    - Supports strict Hybrid-Clean boundaries by keeping inner layers agnostic.
    """

    rx = _provider_regex()
    violations: list[str] = []
    for py in _iter_py_files(BASE_DIR):
        if _is_transitional_allowed(py):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Non-textual file; ignore
            continue
        # Quick skip for empty/near-empty files
        if not text.strip():
            continue
        # Look for provider tokens
        if rx.search(text):
            # Provide a short excerpt for debuggability
            match = rx.search(text)
            start = max(0, match.start() - 30) if match else 0
            end = min(len(text), (match.end() + 30) if match else 0)
            snippet = text[start:end].replace("\n", " ")
            violations.append(f"content mentions provider in {py}: …{snippet}…")

    if violations:
        pytest.xfail(
            "provider mentions found in base/ file contents — transitional xfail until cleanup: "
            + "; ".join(violations)
        )
