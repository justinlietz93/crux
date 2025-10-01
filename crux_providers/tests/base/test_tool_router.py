"""Unit tests for the simple tool router DTO contract and errors."""

from __future__ import annotations

from crux_providers.base.dto.tool_result import ToolResultDTO
from crux_providers.base.tools.router import SimpleToolRouter
from crux_providers.tests.utils import assert_true


def test_invoke_happy_path_str() -> None:
    """Ensure a registered handler returning a string succeeds and returns content as str."""
    router = SimpleToolRouter()

    def echo_str(params: dict) -> str:
        """Echo handler returning a string representation of params."""
        return f"echo:{params.get('msg', '')}"

    router.register("echo", echo_str)
    res: ToolResultDTO = router.invoke("echo", {"msg": "hello"})

    assert_true(res.ok is True, "ok true")
    assert_true(res.name == "echo", "name echoed")
    assert_true(isinstance(res.content, str), "content is str")
    assert_true(res.content == "echo:hello", "content matches")
    assert_true(res.code is None and res.error is None, "no error")


def test_invoke_happy_path_dict() -> None:
    """Ensure a registered handler returning a dict succeeds and returns content as dict."""
    router = SimpleToolRouter()

    def produce_dict(params: dict) -> dict:
        """Return a dict payload for verification of passthrough semantics."""
        return {"echo": params.get("msg", ""), "ok": True}

    router.register("json", produce_dict)
    res: ToolResultDTO = router.invoke("json", {"msg": "world"})

    assert_true(res.ok is True, "ok true")
    assert_true(res.name == "json", "name json")
    assert_true(isinstance(res.content, dict), "content is dict")
    assert_true(res.content == {"echo": "world", "ok": True}, "payload match")
    assert_true(res.code is None and res.error is None, "no error")


def test_invoke_unknown_tool() -> None:
    """Unknown tool names should return a standardized NOT_FOUND error envelope."""
    router = SimpleToolRouter()
    res: ToolResultDTO = router.invoke("missing")
    assert_true(res.ok is False, "ok false")
    assert_true(res.name == "missing", "name missing")
    assert_true(res.code == "NOT_FOUND", "code NOT_FOUND")
    assert_true(isinstance(res.error, str), "error is str")


def test_invoke_exception_path() -> None:
    """Handlers raising exceptions should produce ok=False with code=EXCEPTION."""
    router = SimpleToolRouter()

    def boom(_: dict) -> str:
        """Raise a runtime error to exercise error wrapping."""
        raise RuntimeError("kaboom")

    router.register("boom", boom)

    res: ToolResultDTO = router.invoke("boom", {})

    assert_true(res.ok is False, "ok false")
    assert_true(res.name == "boom", "name boom")
    assert_true(res.code == "EXCEPTION", "code EXCEPTION")
    assert_true(res.error == "kaboom", "error message")
