"""Smoke tests to cover import-only modules and re-export surfaces.

These tests ensure that modules with little to no runtime logic are still
executed by the test suite, preventing 0% coverage files. We validate that
their public exports are present and correctly referenced.
"""

from __future__ import annotations


def test_base_stubs_exports_present():
    """Import ``crux_providers.base.stubs`` and verify its exports exist.

    This confirms re-exports from ``stubs_parts`` are wired and importable.
    """
    print("[imports] validating crux_providers.base.stubs __all__ symbols are present")
    from crux_providers.base import stubs as stubs_mod

    # Explicit boolean checks to satisfy linters that warn on bare asserts.
    has_all = hasattr(stubs_mod, "__all__")
    if not has_all:
        raise AssertionError("stubs module must define __all__")
    missing = [name for name in stubs_mod.__all__ if not hasattr(stubs_mod, name)]
    if missing:
        raise AssertionError(f"Missing re-exports in stubs: {missing}")


def test_openai_style_parts_style_reexports():
    """Import the OpenAI-style re-export shim and verify its symbol surface.

    Ensures ``BaseOpenAIStyleProvider``, ``_ProviderInit``, and
    ``_ChatCompletionsClient`` are exposed for consumer imports.
    """
    print("[imports] validating openai_style_parts.style re-exports")
    from crux_providers.base.openai_style_parts.style import (
        BaseOpenAIStyleProvider,
        _ProviderInit,
        _ChatCompletionsClient,
    )

    # Basic presence checks (avoid instantiation side-effects)
    for sym in (BaseOpenAIStyleProvider, _ProviderInit, _ChatCompletionsClient):
        if sym is None:
            raise AssertionError("exported symbol must be present")
        if not hasattr(sym, "__module__"):
            raise AssertionError("export should be a type or object")


def test_di_imports_and_construction():
    """Import DI entry points and exercise simple construction/clear.

    Avoids provider instantiation to keep side-effects minimal.
    """
    print("[imports] validating DI container import and basic lifecycle")
    from crux_providers.di import build_container, ProvidersContainer

    container = build_container(config={})
    if not isinstance(container, ProvidersContainer):
        raise AssertionError("container must be ProvidersContainer instance")
    # Exercise clear path for a touch more coverage
    container.clear()
