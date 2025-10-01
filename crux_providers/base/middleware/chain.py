"""Middleware chain for provider chat/stream hooks.

Defines a simple, pluggable chain that runs pre/post hooks around provider
operations. Hooks may mutate requests/responses to implement concerns such as
redaction, tagging, or metrics enrichment while keeping provider core logic
clean and consistent with architecture standards.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..logging import LogContext
from ..models import ChatRequest, ChatResponse
from .middleware_base import Middleware


@dataclass
class ChatMiddlewareChain:
    """Composable chain executing middleware hooks in order.

    Attributes:
        items: Ordered list of middleware objects to execute.
    """

    items: List[Middleware]

    def run_before_chat(self, ctx: LogContext, request: ChatRequest) -> ChatRequest:
        """Run ``before_chat`` across the chain in order, returning final request."""
        req = request
        for m in self.items:
            req = m.before_chat(ctx, req)
        return req

    def run_after_chat(self, ctx: LogContext, response: ChatResponse) -> ChatResponse:
        """Run ``after_chat`` across the chain in order, returning final response."""
        resp = response
        for m in self.items:
            resp = m.after_chat(ctx, resp)
        return resp

    def run_before_stream(self, ctx: LogContext, request: ChatRequest) -> ChatRequest:
        """Run ``before_stream`` across the chain in order, returning final request."""
        req = request
        for m in self.items:
            req = m.before_stream(ctx, req)
        return req
