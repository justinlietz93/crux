"""Universal Provider Router with capability-based routing.

This module implements intelligent routing of requests to providers based on
required capabilities, fallback chains, and selective SDK feature usage.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Union

from ..interfaces import (
    LLMProvider,
    SupportsStreaming,
    SupportsToolUse,
    SupportsJSONOutput,
)
from ..models import ChatRequest, ChatResponse
from ..streaming import ChatStreamEvent
from ..capabilities.core import detect_capabilities
from ..errors import ProviderError, ErrorCode


class ProviderRouter:
    """Routes requests to providers based on capabilities and preferences.
    
    This router enables:
    - Capability-based provider selection
    - Fallback chains for reliability
    - Selective feature routing (e.g., use OpenAI for tools, Anthropic for text)
    - Cost optimization routing
    
    Example usage:
        router = ProviderRouter()
        router.register_provider("openai", openai_provider, priority=10)
        router.register_provider("anthropic", anthropic_provider, priority=5)
        
        # Route based on capabilities
        response = router.chat(request, required_capabilities=["streaming", "tool_use"])
    """

    def __init__(self) -> None:
        """Initialize the provider router."""
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._fallback_chains: Dict[str, List[str]] = {}

    def register_provider(
        self,
        provider_id: str,
        provider: LLMProvider,
        priority: int = 0,
        cost_per_1k_tokens: Optional[float] = None,
        capabilities: Optional[frozenset[str]] = None,
    ) -> None:
        """Register a provider with the router.
        
        Parameters
        ----------
        provider_id:
            Unique identifier for the provider.
        provider:
            Provider instance implementing LLMProvider.
        priority:
            Higher priority providers are tried first (default: 0).
        cost_per_1k_tokens:
            Optional cost metric for routing decisions.
        capabilities:
            Optional explicit capability set; auto-detected if None.
        """
        detected_caps = capabilities or detect_capabilities(provider)
        self._providers[provider_id] = {
            "provider": provider,
            "priority": priority,
            "cost": cost_per_1k_tokens,
            "capabilities": detected_caps,
        }

    def set_fallback_chain(
        self,
        primary_id: str,
        fallback_ids: List[str],
    ) -> None:
        """Configure fallback providers for a primary provider.
        
        Parameters
        ----------
        primary_id:
            Primary provider identifier.
        fallback_ids:
            List of provider IDs to try in order if primary fails.
        """
        self._fallback_chains[primary_id] = fallback_ids

    def chat(
        self,
        request: ChatRequest,
        required_capabilities: Optional[List[str]] = None,
        preferred_provider: Optional[str] = None,
        optimize_for: str = "priority",
    ) -> ChatResponse:
        """Route a chat request to the best available provider.
        
        Parameters
        ----------
        request:
            Chat request to execute.
        required_capabilities:
            Optional list of required capabilities (e.g., ["streaming", "tool_use"]).
        preferred_provider:
            Optional provider ID to prefer if it meets requirements.
        optimize_for:
            Routing strategy: "priority", "cost", "capability_match".
            
        Returns
        -------
        ChatResponse
            Response from the selected provider.
            
        Raises
        ------
        ProviderError:
            When no provider meets the requirements or all providers fail.
        """
        candidates = self._select_candidates(
            required_capabilities=required_capabilities,
            preferred_provider=preferred_provider,
            optimize_for=optimize_for,
        )

        last_error = None
        for provider_id in candidates:
            provider_info = self._providers[provider_id]
            provider = provider_info["provider"]
            
            try:
                return provider.chat(request)
            except Exception as e:
                last_error = e
                # Try fallback if configured
                if provider_id in self._fallback_chains:
                    for fallback_id in self._fallback_chains[provider_id]:
                        if fallback_id in self._providers:
                            try:
                                fallback_provider = self._providers[fallback_id]["provider"]
                                return fallback_provider.chat(request)
                            except Exception:
                                continue

        raise ProviderError(
            code=ErrorCode.INTERNAL,
            message=f"All providers failed. Last error: {last_error}",
            provider="router",
        )

    def stream_chat(
        self,
        request: ChatRequest,
        required_capabilities: Optional[List[str]] = None,
        preferred_provider: Optional[str] = None,
    ) -> Iterator[ChatStreamEvent]:
        """Route a streaming chat request to the best available provider.
        
        Parameters
        ----------
        request:
            Chat request to execute.
        required_capabilities:
            Optional list of required capabilities (must include "streaming").
        preferred_provider:
            Optional provider ID to prefer.
            
        Yields
        ------
        ChatStreamEvent
            Stream events from the selected provider.
            
        Raises
        ------
        ProviderError:
            When no streaming provider is available.
        """
        req_caps = required_capabilities or []
        if "streaming" not in req_caps:
            req_caps.append("streaming")

        candidates = self._select_candidates(
            required_capabilities=req_caps,
            preferred_provider=preferred_provider,
        )

        for provider_id in candidates:
            provider_info = self._providers[provider_id]
            provider = provider_info["provider"]
            
            if isinstance(provider, SupportsStreaming) and provider.supports_streaming():
                try:
                    yield from provider.stream_chat(request)
                    return
                except Exception:
                    continue

        raise ProviderError(
            code=ErrorCode.INTERNAL,
            message="No streaming provider available",
            provider="router",
        )

    def execute_with_tools(
        self,
        request: ChatRequest,
        tools: List[dict],
        preferred_provider: Optional[str] = None,
    ) -> ChatResponse:
        """Execute a request with tool use capability.
        
        Parameters
        ----------
        request:
            Chat request.
        tools:
            Tool definitions.
        preferred_provider:
            Optional preferred provider.
            
        Returns
        -------
        ChatResponse
            Response potentially containing tool calls.
        """
        candidates = self._select_candidates(
            required_capabilities=["tool_use"],
            preferred_provider=preferred_provider,
        )

        for provider_id in candidates:
            provider = self._providers[provider_id]["provider"]
            
            if isinstance(provider, SupportsToolUse) and provider.supports_tool_use():
                try:
                    return provider.execute_with_tools(request, tools)
                except Exception:
                    continue

        # Fallback: use regular chat if no tool provider available
        return self.chat(request, preferred_provider=preferred_provider)

    def _select_candidates(
        self,
        required_capabilities: Optional[List[str]] = None,
        preferred_provider: Optional[str] = None,
        optimize_for: str = "priority",
    ) -> List[str]:
        """Select candidate providers based on requirements.
        
        Returns provider IDs sorted by preference.
        """
        candidates = []
        
        for provider_id, info in self._providers.items():
            # Check if provider meets capability requirements
            if required_capabilities:
                provider_caps = info["capabilities"]
                if not all(cap in provider_caps for cap in required_capabilities):
                    continue
            
            candidates.append((provider_id, info))

        # Prioritize preferred provider if it meets requirements
        if preferred_provider and preferred_provider in self._providers:
            if any(pid == preferred_provider for pid, _ in candidates):
                candidates = [
                    (pid, info) for pid, info in candidates if pid == preferred_provider
                ] + [
                    (pid, info) for pid, info in candidates if pid != preferred_provider
                ]

        # Sort by optimization strategy
        if optimize_for == "cost":
            candidates.sort(key=lambda x: (x[1].get("cost") or float("inf"), -x[1]["priority"]))
        else:  # priority
            candidates.sort(key=lambda x: (-x[1]["priority"], x[1].get("cost") or 0))

        return [pid for pid, _ in candidates]

    def list_providers(
        self,
        capability_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List registered providers with their capabilities.
        
        Parameters
        ----------
        capability_filter:
            Optional capability requirements for filtering.
            
        Returns
        -------
        List[Dict[str, Any]]
            Provider metadata including capabilities.
        """
        result = []
        for provider_id, info in self._providers.items():
            if capability_filter:
                if not all(cap in info["capabilities"] for cap in capability_filter):
                    continue
            
            result.append({
                "id": provider_id,
                "priority": info["priority"],
                "cost": info["cost"],
                "capabilities": list(info["capabilities"]),
            })
        
        return result


__all__ = ["ProviderRouter"]
