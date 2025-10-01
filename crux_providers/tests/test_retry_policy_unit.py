from __future__ import annotations

import time
import pytest

from crux_providers.base.errors import ErrorCode, ProviderError
from crux_providers.base.resilience.retry import (
    RetryConfig,
    retry,
)


class _Flaky:
    def __init__(self, fail_times: int, code: ErrorCode):
        self.calls = 0
        self.fail_times = fail_times
        self.code = code

    def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError(code=self.code, message="boom", provider="x")
        return "ok"


def test_retry_succeeds_after_transient(monkeypatch):
    # Make sleep fast
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    attempt_log = []

    def attempt_logger(**kw):
        attempt_log.append(kw)

    cfg = RetryConfig(max_attempts=3, delay_base=1.0, attempt_logger=attempt_logger)

    flaky = _Flaky(fail_times=2, code=ErrorCode.TRANSIENT)

    @retry(cfg)
    def run():
        return flaky()

    assert run() == "ok"  # nosec B101 - asserts are appropriate in unit tests
    # Should have been called 3 times total (2 failures + 1 success)
    assert flaky.calls == 3  # nosec B101 - asserts are appropriate in unit tests
    # Attempt logger should have entries; last one has error=None
    assert any(e["error"] is None for e in attempt_log)  # nosec B101 - asserts are appropriate in unit tests


def test_retry_stops_on_non_retryable():
    cfg = RetryConfig(max_attempts=4, delay_base=1.0)
    flaky = _Flaky(fail_times=99, code=ErrorCode.VALIDATION)

    @retry(cfg)
    def run():
        return flaky()

    with pytest.raises(ProviderError) as ei:
        run()
    assert ei.value.code is ErrorCode.VALIDATION  # nosec B101 - asserts are appropriate in unit tests
    # Should not exhaust all attempts because non-retryable
    assert flaky.calls == 1  # nosec B101 - asserts are appropriate in unit tests
