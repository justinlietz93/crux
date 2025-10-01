"""Provider Factory utilities.

Purpose
-------
Centralize provider-agnostic creation of adapter instances implementing the
``LLMProvider`` interface. Adapters are imported lazily using ``importlib`` to
avoid heavy imports at module import time and to keep side effects out of the
factory layer.

External dependencies
---------------------
- Standard library only (``importlib``). Provider adapters themselves may
    depend on external SDKs, but are imported on-demand.

Timeout and fallback semantics
------------------------------
- No timeouts are introduced here. The factory performs no retries or
    fallbacks; it either returns an instance or raises a clear error.

Scope
-----
Supported providers include: ``openai``, ``anthropic``, ``gemini``,
``deepseek``, ``openrouter``, ``ollama``, and ``xai``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Mapping, Optional, Tuple, Type

from .dto.adapter_params import AdapterParams


class UnknownProviderError(Exception):
    """Raised when a provider cannot be resolved or initialized.

    This exception signals errors in provider lookup or adapter initialization
    within the :class:`ProviderFactory`.

    Failure modes include:
    - The provider name is not registered in the factory mapping.
    - The provider module cannot be imported or the adapter class is missing.
    - The adapter constructor raised an exception during initialization.
    """

def create_provider(provider: str, **kwargs: Any) -> Any:
    """Compatibility helper that delegates to :meth:`ProviderFactory.create`.

    Parameters
    ----------
    provider:
        Canonical provider identifier (e.g., ``"openai"``).
    **kwargs:
        Adapter-specific keyword arguments forwarded to the provider adapter
        constructor.

    Returns
    -------
    Any
        A concrete instance that implements ``LLMProvider``.
    """
    return ProviderFactory.create(provider, **kwargs)


class ProviderFactory:
    """Create provider adapters based on a canonical name (e.g., ``"openai"``).

    Design notes
    ------------
    - Uses ``importlib.import_module`` for explicit import semantics.
    - Raises :class:`UnknownProviderError` with precise, actionable messages
      for unknown providers, import failures, missing classes, and constructor
      errors.
    - Maintains backward compatibility with the top-level ``create_provider``
      helper.
    """

    # Map canonical provider names to import paths and class names
    _PROVIDERS: Dict[str, Dict[str, str]] = {
        "openai": {"module": "crux_providers.openai.client", "class": "OpenAIProvider"},
        "anthropic": {"module": "crux_providers.anthropic.client", "class": "AnthropicProvider"},
        "gemini": {"module": "crux_providers.gemini.client", "class": "GeminiProvider"},
        "deepseek": {"module": "crux_providers.deepseek.client", "class": "DeepseekProvider"},
        "openrouter": {"module": "crux_providers.openrouter.client", "class": "OpenRouterProvider"},
        "ollama": {"module": "crux_providers.ollama.client", "class": "OllamaProvider"},
        "xai": {"module": "crux_providers.xai.client", "class": "XAIProvider"},
    }

    @classmethod
    def create(
        cls,
        provider: str,
        *,
        params: Optional[AdapterParams] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a provider adapter instance.

        Parameters
        ----------
        provider:
            Canonical provider name (e.g., ``"openai"``).
        params:
            Optional structured :class:`AdapterParams` instance; merged into
            legacy ``kwargs`` with explicit kwargs taking precedence.
        **kwargs:
            Adapter-specific constructor kwargs (optional).

        Returns
        -------
        Any
            Instance implementing ``LLMProvider``.

        Raises
        ------
        UnknownProviderError
            If provider is unknown, the adapter module fails to import, the
            adapter class is missing, or the adapter constructor raises.
        """
        # Merge typed params into kwargs for backward compatibility
        merged_kwargs = cls._coerce_params(params, kwargs)

        name = (provider or "").lower().strip()
        spec = cls._PROVIDERS.get(name)
        if not spec:
            raise UnknownProviderError(f"Unknown provider '{provider}'")

        module_path, class_name = spec["module"], spec["class"]

        # Import the provider module explicitly (clear error if import fails)
        try:
            mod = import_module(module_path)
        except Exception as exc:  # pragma: no cover - import failure path
            raise UnknownProviderError(
                f"Failed to import module '{module_path}' for provider '{provider}': {exc}"
            ) from exc

        # Retrieve the adapter class from the module
        try:
            klass: Type = getattr(mod, class_name)
        except AttributeError as exc:
            raise UnknownProviderError(
                f"Adapter class '{class_name}' not found in '{module_path}' for provider '{provider}'"
            ) from exc

        # Construct the adapter with merged kwargs, surfacing constructor errors
        try:
            return klass(**merged_kwargs)  # type: ignore[call-arg]
        except TypeError as exc:
            raise UnknownProviderError(
                f"Invalid arguments for '{provider}' adapter constructor: {exc}"
            ) from exc
        except Exception as exc:  # pragma: no cover - adapter runtime init error
            raise UnknownProviderError(
                f"Failed to initialize provider '{provider}': {exc}"
            ) from exc

    @classmethod
    def supported(cls) -> Tuple[str, ...]:
        """Return the tuple of supported canonical provider names.

        Returns
        -------
        tuple[str, ...]
            Canonical provider names in deterministic order.
        """
        return tuple(cls._PROVIDERS.keys())

    @staticmethod
    def _coerce_params(params: Optional[AdapterParams], kwargs: Mapping[str, Any]) -> Dict[str, Any]:
        """Merge ``AdapterParams`` into legacy ``kwargs``.

        Contract
        --------
        - Values explicitly provided in ``kwargs`` take precedence over ``params``.
        - Only defined fields from ``AdapterParams`` are merged; ``None`` values
          are ignored to avoid overwriting adapter defaults.
        - ``extra`` mapping (if present) is shallow-merged with any existing
          ``extra`` in kwargs, with kwargs winning conflicts.

        Parameters
        ----------
        params:
            Optional typed parameter object.
        kwargs:
            Arbitrary keyword arguments from legacy call sites.

        Returns
        -------
        dict
            A new dictionary safe to pass to adapter constructors.
        """
        if params is None:
            return dict(kwargs)
        merged: Dict[str, Any] = dict(params.model_dump(exclude_none=True))
        # Ensure adapter constructors don't receive unexpected 'provider'
        merged.pop("provider", None)
        # Merge shallow headers/extra properly with kwargs precedence
        if "headers" in merged and "headers" in kwargs:
            h = dict(merged["headers"])  # type: ignore[arg-type]
            h |= kwargs["headers"]
            merged["headers"] = h
        if "extra" in merged and "extra" in kwargs:
            e = dict(merged["extra"])  # type: ignore[arg-type]
            e.update(kwargs["extra"])  # kwargs wins
            merged["extra"] = e
        # Finally overlay kwargs (explicit always wins)
        merged.update(kwargs)
        return merged
