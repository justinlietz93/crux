from __future__ import annotations

import pytest

from crux_providers.base.factory import ProviderFactory, UnknownProviderError


def test_factory_unknown_provider():
    with pytest.raises(UnknownProviderError):
        ProviderFactory.create("nope")


def test_factory_import_failure(monkeypatch):
    # Register a bogus provider to hit the import error path
    monkeypatch.setattr(
        ProviderFactory,
        "_PROVIDERS",
        {"bogus": {"module": "does.not.exist", "class": "X"}},
        raising=False,
    )
    with pytest.raises(UnknownProviderError):
        ProviderFactory.create("bogus")
