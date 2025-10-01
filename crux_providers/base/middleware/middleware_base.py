"""Base class for provider middleware hooks.

This module defines the `Middleware` base class used by provider chat/stream
pipelines. It provides no-op implementations for all hooks so implementers can
override only the methods they need without relying on dynamic introspection.

Design goals:
- Avoid dynamic `getattr`/`hasattr` checks by guaranteeing hook presence.
- Keep hooks fast and side-effect free (no network I/O) to preserve latency.
- Maintain compatibility with the clean architecture guidelines and the rule of
  one-class-per-file.
"""

from __future__ import annotations

from ..logging import LogContext
from ..models import ChatRequest, ChatResponse


class Middleware:
    """Base middleware with no-op hooks for chat and streaming.

    Subclass this and override any of the hooks to implement concerns like
    redaction, tagging, or metrics enrichment. Each method returns the provided
    object (request/response), allowing chained transformations.

    Failure modes:
    - Implementations may raise exceptions (e.g., `ValueError`) to abort the
      operation. Callers decide how to surface these errors.

    Performance notes:
    - Hooks should be fast and pure. Avoid blocking I/O or long-running work.
    """

    def before_chat(self, ctx: LogContext, request: ChatRequest) -> ChatRequest:
        """Called before a non-streaming chat operation.

        Parameters:
            ctx: Structured log context for the current provider operation.
            request: The chat request to be processed.

        Returns:
            The (possibly) modified chat request.
        """

        return request

    def after_chat(self, ctx: LogContext, response: ChatResponse) -> ChatResponse:
        """Called after a non-streaming chat operation.

        Parameters:
            ctx: Structured log context for the current provider operation.
            response: The chat response produced by the provider.

        Returns:
            The (possibly) modified chat response.
        """

        return response

    def before_stream(self, ctx: LogContext, request: ChatRequest) -> ChatRequest:
        """Called before a streaming chat operation begins.

        Parameters:
            ctx: Structured log context for the current provider operation.
            request: The chat request that will be used to start the stream.

        Returns:
            The (possibly) modified chat request.
        """

        return request
