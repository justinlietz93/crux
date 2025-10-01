"""Policy test: enforce <=500 LOC per source file with explicit deviations.

This test guards the architectural rule that no single source file should
exceed 500 lines. Known exceptions must be explicitly allow-listed with a
documented deviation rationale and a revisit date.

Note that counting includes docstrings and comments, which is acceptable for
this coarse policy. The intent is to keep modules focused and maintainable.
"""

from __future__ import annotations

from pathlib import Path
import pytest


MAX_LOC = 500

# deviation: file-size reason=Pending provider class decomposition revisit=2025-10-15
ALLOWLIST = {
    # Large provider adapter slated for decomposition into submodules
    "crux_providers/openrouter/client.py",
    # deviation: file-size reason=Pending provider class decomposition revisit=2025-10-15
    "crux_providers/anthropic/client.py",
    # deviation: file-size reason=Base OpenAI-style provider consolidation; split by concerns revisit=2025-10-15
    "crux_providers/base/openai_style.py",
    # deviation: file-size reason=Provider adapter decomposition pending revisit=2025-10-15
    "crux_providers/ollama/client.py",
}


def test_source_files_line_count_budget() -> None:
    """Fail if any provider source file exceeds the MAX_LOC budget.

    Skips tests and dunders; allow-listed files are temporarily excluded with
    an inline deviation marker that includes reason and revisit date.
    """
    root = Path(__file__).resolve().parents[3]  # repo root
    pkg = root / "productivity_tools" / "providers"
    offenders: list[tuple[str, int]] = []
    for p in pkg.rglob("*.py"):
        rel = str(p.relative_to(root))
        if rel in ALLOWLIST:
            continue
        # Skip __init__ and tests from policy enforcement
        if "/tests/" in rel or p.name == "__init__.py":
            continue
        with p.open("r", encoding="utf-8") as fh:
            loc = sum(1 for _ in fh)
        if loc > MAX_LOC:
            offenders.append((rel, loc))

    if offenders:
        pytest.fail(f"Files over {MAX_LOC} LOC: {offenders}")
