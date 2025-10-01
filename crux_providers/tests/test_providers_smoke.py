"""Basic smoke tests for providers package and factory registration."""
from __future__ import annotations

import importlib
import pytest


def test_import_and_version():
    mod = importlib.import_module("crux_providers")
    assert hasattr(mod, "__version__")  # nosec B101 test assertion
    assert isinstance(mod.__version__, str)  # nosec B101 test assertion


def test_create_symbol_present():
    mod = importlib.import_module("crux_providers")
    assert hasattr(mod, "create")  # nosec B101 test assertion


@pytest.mark.parametrize(
    "provider_name",
    ["openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "xai"],
)
def test_factory_provider_registration(provider_name):
    from crux_providers import ProviderFactory

    pf = ProviderFactory()
    assert provider_name in pf._PROVIDERS  # nosec B101 test assertion  # type: ignore[attr-defined]
