"""Global middleware chain registry for provider chat/stream hooks.

Separates global state management from the chain implementation to keep
dependencies minimal and respect one-class-per-file guidance.
"""

from __future__ import annotations

from .chain import ChatMiddlewareChain

_GLOBAL_CHAIN: ChatMiddlewareChain = ChatMiddlewareChain(items=[])


def set_global_middleware(chain: ChatMiddlewareChain) -> None:
    """Set the global middleware chain used by base providers.

    Side effects:
        Mutates module-level state to point to the provided chain.
    """

    global _GLOBAL_CHAIN
    _GLOBAL_CHAIN = chain


def get_middleware_chain() -> ChatMiddlewareChain:
    """Return the global middleware chain (empty by default)."""

    return _GLOBAL_CHAIN
