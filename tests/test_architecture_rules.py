"""Architecture enforcement tests for Hybrid-Clean Architecture constraints.

This module provides lightweight, repository-local invariants to ensure
that the providers package remains decoupled from outer layers (e.g.,
service/presentation). It focuses on import boundaries only and is designed
to fail fast if a forbidden dependency is introduced.

Rules validated here:
1) Providers must not import from `productivity_tools.provider_service` (or submodules).
   - Presentation/server concerns should not bleed into providers (infrastructure layer).

These tests are intentionally static-file scans to avoid import-time side
effects, and they emit clear failure messages for quick remediation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


def _iter_python_files(root: Path) -> Iterable[Path]:
    """Yield all Python source files under a root directory.

    Parameters
    ----------
    root: Path
        The directory to scan recursively.

    Yields
    ------
    Path
        Absolute paths to ``.py`` files under the provided root, skipping
        common non-source directories (e.g., ``__pycache__``).
    """

    for path in root.rglob("*.py"):
        # Skip bytecode caches or other irrelevant directories
        if "__pycache__" in path.parts:
            continue
        yield path


def _read_text(path: Path) -> str:
    """Read a file as UTF-8 text.

    Parameters
    ----------
    path: Path
        File path to read.

    Returns
    -------
    str
        The full file contents as text. On decoding problems, uses replacement
        to ensure the scan can continue deterministically.
    """

    return path.read_text(encoding="utf-8", errors="replace")


def test_providers_do_not_import_outer_layers() -> None:
    """Ensure provider modules do not import presentation/service layers.

    Contract
    --------
    - Scope: Only scans files under ``productivity_tools/providers``.
    - Forbidden imports (exact substrings in source):
      * ``from productivity_tools.provider_service``
      * ``import productivity_tools.provider_service``

    Failure mode
    ------------
    The test fails with a clear message listing offending files and the
    matched forbidden import. This protects the inward-only dependency
    direction required by our Hybrid-Clean Architecture.
    """

    import pytest

    repo_root = Path(__file__).resolve().parent.parent
    # Prefer legacy path if present, otherwise scan the consolidated providers package
    candidates = [
        repo_root / "productivity_tools" / "providers",
        repo_root / "crux_providers",
    ]
    providers_root = next((p for p in candidates if p.is_dir()), None)
    if providers_root is None:
        pytest.skip("No providers directory found (productivity_tools/providers or crux_providers); skipping boundary check")

    forbidden_snippets: List[str] = [
        "from productivity_tools.provider_service",
        "import productivity_tools.provider_service",
    ]

    offenders: List[str] = []

    for py in _iter_python_files(providers_root):
        src = _read_text(py)
        matches = [snippet for snippet in forbidden_snippets if snippet in src]
        if matches:
            offenders.extend(f"{py}: contains '{m}'" for m in matches)

    if offenders:
        pytest.fail(
            "Providers must not import outer layers (service/presentation).\n" + "\n".join(offenders)
        )
