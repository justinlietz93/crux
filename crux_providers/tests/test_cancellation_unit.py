"""Unit tests for cooperative cancellation primitives.

Covers idempotent cancel, cascade to children, late link of child after
parent cancel, and raise_if_cancelled behavior.
"""
from __future__ import annotations

import pytest

from crux_providers.base.cancellation import (
    CancellationToken,
    CancelledError,
)


def test_cancel_cascades_to_children_and_is_idempotent():
    parent = CancellationToken()
    child1 = parent.child()
    child2 = parent.child()

    parent.cancel(reason="stop")
    # idempotent second call
    parent.cancel(reason="ignored")

    assert parent.cancelled is True and parent.reason == "stop"  # nosec B101 - pytest assert in tests
    assert child1.cancelled is True and child1.reason == "stop"  # nosec B101 - pytest assert in tests
    assert child2.cancelled is True and child2.reason == "stop"  # nosec B101 - pytest assert in tests


def test_link_child_after_parent_cancel_immediately_cancels_child():
    parent = CancellationToken()
    parent.cancel("done")
    late_child = CancellationToken(parent=parent)
    assert late_child.cancelled is True and late_child.reason == "done"  # nosec B101 - pytest assert in tests


def test_raise_if_cancelled_raises_custom_error():
    token = CancellationToken()
    token.cancel("terminate")
    with pytest.raises(CancelledError):
        token.raise_if_cancelled()
