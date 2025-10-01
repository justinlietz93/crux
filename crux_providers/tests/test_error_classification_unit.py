from __future__ import annotations

import types

from crux_providers.base.errors import (
    ErrorCode,
    ProviderError,
    classify_exception,
)


def test_classify_provider_error_passthrough():
    e = ProviderError(code=ErrorCode.AUTH, message="nope", provider="x")
    assert classify_exception(e) is ErrorCode.AUTH  # nosec B101 - assert is appropriate in unit tests


def test_classify_http_status_mapping():
    # Direct attr
    e1 = types.SimpleNamespace(status_code=404)
    assert classify_exception(e1) is ErrorCode.NOT_FOUND  # nosec B101 - assert is appropriate in unit tests
    # response.status_code
    e2 = types.SimpleNamespace(response=types.SimpleNamespace(status_code=503))
    assert classify_exception(e2) is ErrorCode.UNAVAILABLE  # nosec B101 - assert is appropriate in unit tests


def test_classify_heuristics():
    assert classify_exception(Exception("rate limit exceeded")) is ErrorCode.RATE_LIMIT  # nosec B101 - assert is appropriate in unit tests
    assert classify_exception(Exception("timed out waiting")) is ErrorCode.TIMEOUT  # nosec B101 - assert is appropriate in unit tests
    assert classify_exception(Exception("unsupported parameter")) is ErrorCode.UNSUPPORTED  # nosec B101 - assert is appropriate in unit tests
    assert classify_exception(Exception("random")) is ErrorCode.UNKNOWN  # nosec B101 - assert is appropriate in unit tests
