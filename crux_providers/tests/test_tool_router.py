"""Unit tests for the SimpleToolRouter tool invocation stub.

Covers happy path, unknown tool, and exception handling paths.
"""

from __future__ import annotations

from crux_providers.base.tools.router import SimpleToolRouter


def test_happy_path_returns_content():
    router = SimpleToolRouter()

    def echo(params: dict):
        return {"echo": params.get("value", "")}

    router.register("echo", echo)
    res = router.invoke("echo", {"value": "hello"})
    assert res.ok is True  # nosec B101
    assert res.name == "echo"  # nosec B101
    assert isinstance(res.content, dict) and res.content["echo"] == "hello"  # nosec B101


def test_unknown_tool_returns_not_found():
    router = SimpleToolRouter()
    res = router.invoke("nope")
    assert res.ok is False  # nosec B101
    assert res.code == "NOT_FOUND"  # nosec B101


def test_tool_exception_captured():
    router = SimpleToolRouter()

    def boom(params: dict):
        raise RuntimeError("boom")

    router.register("boom", boom)
    res = router.invoke("boom")
    assert res.ok is False  # nosec B101
    assert res.code == "EXCEPTION"  # nosec B101
    assert "boom" in (res.error or "")  # nosec B101
