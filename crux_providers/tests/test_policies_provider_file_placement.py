"""Policy test: provider-specific files must live in their subpackages.

This enforces the architectural rule that any provider-specific code/files
(e.g., names containing "openai", "anthropic", etc.) are not placed in
generic/shared modules. The allowed exceptions are generic, multi-provider
building blocks in the base package (e.g., "openai_style" helpers used by
multiple OpenAI-style providers).

Failure mode:
- If any Python file outside the provider subpackages contains a provider
  name in its filename (e.g., ``base/openai_utils.py``), the test fails with
  a list of offending file paths to relocate or rename.

This test is intentionally simple and fast; it scans only filenames and
does not parse imports. Keeping the rule filename-based avoids false
positives from docstrings or comments and matches the governance intent.
"""

from __future__ import annotations

from pathlib import Path
import pytest


def test_provider_files_are_in_designated_packages() -> None:
  """Ensure provider-named files are not placed outside their packages.

  Rule:
  - Provider-specific names: [openai, anthropic, deepseek, openrouter,
    gemini, xai, ollama]
  - These names are allowed under their matching subpackages only, e.g.,
    ``crux_providers/openai/``.
  - Allowed exceptions (generic building blocks used across providers):
    - ``crux_providers/base/openai_style.py``
    - ``crux_providers/base/openai_style_parts/`` subtree

  The test scans Python filenames. If a filename contains a provider name
  but is not located within the corresponding package, and is not an
  allowed exception, it is flagged.
  """

  repo_root = Path(__file__).resolve().parents[2]
  pkg_root = repo_root / "crux_providers"

  provider_names = [
    "openai",
    "anthropic",
    "deepseek",
    "openrouter",
    "gemini",
    "xai",
    "ollama",
  ]

  # Exceptions: generic building blocks that intentionally include a
  # provider keyword but serve multiple providers in the base package.
  allowed_substrings = [
    "/crux_providers/base/openai_style.py",
    "/crux_providers/base/openai_style_parts/",
    "/crux_providers/base/openai_structured.py",
    "/crux_providers/base/openai_style_helpers.py",
    "/crux_providers/base/stubs_parts/openai/",
    "/crux_providers/base/stubs_parts/anthropic/",
  ]

  offenders: list[str] = []

  for py in pkg_root.rglob("*.py"):
    # Normalize path for substring checks
    p = py.as_posix()

    # Skip test files and package markers
    if "/tests/" in p or p.endswith("/__init__.py"):
      continue

    # If path already resides under an explicit provider folder, it's OK
    if any(f"/crux_providers/{name}/" in p for name in provider_names):
      continue

    # Allow documented base exceptions
    if any(allowed in p for allowed in allowed_substrings):
      continue

    # Flag filenames that contain a provider name (case-sensitive match)
    filename = py.name
    if any(name in filename for name in provider_names):
      offenders.append(p)

  if offenders:
    pytest.fail(
      "Provider-specific files must live in their designated subpackages.\n"
      "Move or rename these files to comply with architecture policy:\n- "
      + "\n- ".join(offenders)
    )
