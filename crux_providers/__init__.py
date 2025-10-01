"""crux_providers package

Unified abstraction surface for multiple AI model providers.

Purpose:
    Provide a minimal, stable API for external consumption (packaging is
    configured via the repository root ``pyproject.toml``). Legacy helper paths
    were removed to avoid technical debt. Callers are expected to use provider
    instances directly (for example, ``create('openai').chat(...)``).

Public API (re-exported):
    - Version: ``__version__``
    - Exceptions: :class:`ProviderError`, :class:`ErrorCode`
    - Factory: :func:`create`
    - Optional abstractions (exported if import succeeds): ``ProviderFactory``,
      ``LLMProvider``, ``SupportsJSONOutput``, ``SupportsResponsesAPI``,
      ``ModelListingProvider``, ``HasDefaultModel``

Notes:
    - Future expansion may leverage plugin entry points under
      ``crux_providers.plugins`` for third‑party adapter registration.
"""

import logging
import json
import re
from typing import Dict, Any, Tuple, Union, Optional

# Re-export error types (new taxonomy)
from .base.errors import (
    ProviderError,
    ErrorCode,
)

# Base abstractions (optional exports). Guard imports in case of refactors.
try:  # pragma: no cover - defensive
    from .base.factory import ProviderFactory  # type: ignore
    from .base.dto import AdapterParams  # type: ignore
    from .base.get_models_base import load_cached_models, save_provider_models  # type: ignore
    from .base.interfaces import (  # type: ignore
        LLMProvider,
        SupportsJSONOutput,
        SupportsResponsesAPI,
        ModelListingProvider,
        HasDefaultModel,
    )
except Exception:  # pragma: no cover
    ProviderFactory = None  # type: ignore
    load_cached_models = None  # type: ignore
    save_provider_models = None  # type: ignore
    LLMProvider = SupportsJSONOutput = SupportsResponsesAPI = ModelListingProvider = HasDefaultModel = None  # type: ignore
    AdapterParams = None  # type: ignore

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Exceptions
    "ProviderError",
    "ErrorCode",
    # Core helpers
    "create",
    # Convenience
    "simple",
    # Base (optional) abstractions
    "ProviderFactory",
    "LLMProvider",
    "SupportsJSONOutput",
    "SupportsResponsesAPI",
    "ModelListingProvider",
    "HasDefaultModel",
    # Registry helpers
    "load_cached_models",
    "save_provider_models",
    "AdapterParams",
]

logger = logging.getLogger(__name__)

# Convenience helper export (import-local to avoid heavy imports at module load)
try:  # pragma: no cover - thin re-export
    from .base.utils.simple import simple  # type: ignore
except Exception:  # pragma: no cover
    def simple(*args, **kwargs):  # type: ignore
        """Fallback stub when the convenience helper is unavailable.

        This function exists solely to provide a predictable failure mode when
        ``crux_providers.base.utils.simple`` is not importable in a given
        distribution build. It always raises :class:`ProviderError` so that
        callers do not inadvertently rely on missing optional features.
        """
        raise ProviderError(ErrorCode.UNSUPPORTED, "simple helper unavailable", provider="unknown")


def _safe_format(template: str, context: Dict[str, Any]) -> str:
    """Best-effort brace-style templating without raising on missing keys.

    Summary:
        Safely interpolates keys from ``context`` into ``template`` using
        Python's ``str.format_map`` with a permissive mapping that leaves
        unknown placeholders unchanged. Values are coerced to strings. This is
        more robust than a naive ``str.replace`` loop and preserves the
        ``{placeholder}`` syntax expected by existing templates.

    Parameters:
        template: The input template containing ``{placeholders}``.
        context: Mapping of placeholder names to replacement values.

    Returns:
        A formatted string where known placeholders are replaced. Unknown
        placeholders remain intact (e.g., ``{missing}`` stays as-is). On any
        unexpected error, the original template is returned unchanged.

    Notes:
        - Escaped braces (``{{`` and ``}}``) retain standard ``str.format``
          behavior.
        - This function never raises; errors are logged at debug level.
    """
    class _SafeDict(dict):
        """Dict that returns the original ``{key}`` text for missing keys.

        This mirrors ``collections.defaultdict``-like behavior tailored for
        ``str.format_map`` so that unknown placeholders do not trigger
        ``KeyError`` and instead pass through unchanged.
        """

        def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
            return "{" + key + "}"

    try:
        str_values = {k: str(v) for k, v in context.items()}
        return template.format_map(_SafeDict(str_values))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"Safe format failed: {e}")
        return template


def _clean_json_markers(s: str) -> str:
    """Strip common Markdown code fences from LLM JSON replies.

    Parameters:
        s: Raw string potentially wrapped in triple backtick fences
           (```json ... ``` or ``` ... ```).

    Returns:
        The input string with leading/trailing code fences removed and
        surrounding whitespace trimmed.
    """
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def _attempt_json_repair(s: str) -> str:
    """Best-effort normalization of nearly-JSON strings to parseable JSON.

    Summary:
        Applies conservative, order-dependent cleanups commonly needed for
        LLM responses that are intended to be JSON but include light
        formatting artifacts. The function is intentionally defensive and
        never raises; when repair is not possible it returns the best
        intermediate representation for upstream logging/inspection.

    Steps:
        1. Remove Markdown code fences if present.
        2. Trim leading text before the first ``{`` or ``[``.
        3. Remove trailing commas immediately before ``}`` or ``]``.
        4. Balance unmatched braces/brackets by appending closers.
        5. Ensure an even count of unescaped double quotes.

    Parameters:
        s: Raw model output expected to contain JSON content.

    Returns:
        A normalized string that is more likely to succeed with ``json.loads``.
    """
    # 1) Strip code fences and surrounding whitespace
    s = _clean_json_markers(s)

    # 2) Trim to JSON envelope start if leading commentary exists
    first_obj = s.find("{")
    first_arr = s.find("[")
    if idx_candidates := [i for i in [first_obj, first_arr] if i != -1]:
        start = min(idx_candidates)
        s = s[start:]

    def _drop_trailing_commas(text: str) -> str:
        """Remove commas immediately before a closing brace/bracket.

        This is applied multiple times since subsequent balancing may add
        closers that expose an earlier dangling comma.
        """
        return re.sub(r",\s*(\}|\])", r"\1", text)

    # 3) First pass: remove trailing commas like {"a":1,} or [1,2,]
    s = _drop_trailing_commas(s)

    # 4) Ensure even number of unescaped double quotes BEFORE balancing braces
    def _count_unescaped_quotes(text: str) -> int:
        cnt = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '"':
                # Count preceding backslashes
                bs = 0
                j = i - 1
                while j >= 0 and text[j] == "\\":
                    bs += 1
                    j -= 1
                if bs % 2 == 0:  # not escaped
                    cnt += 1
            i += 1
        return cnt

    if _count_unescaped_quotes(s) % 2 == 1:
        s += '"'

    # Helper: count braces/brackets ignoring those inside string literals
    def _counts_ignoring_strings(text: str) -> tuple[int, int, int, int]:
        in_str = False
        escapes = 0
        ob = cb = osq = csq = 0  # { } [ ] counts
        for ch in text:
            if ch == '"' and escapes % 2 == 0:
                in_str = not in_str
            if in_str:
                if ch == "\\":
                    escapes += 1
                else:
                    escapes = 0
                continue
            # outside strings
            if ch == '{':
                ob += 1
            elif ch == '}':
                cb += 1
            elif ch == '[':
                osq += 1
            elif ch == ']':
                csq += 1
        return ob, cb, osq, csq

    ob, cb, osq, csq = _counts_ignoring_strings(s)
    if ob > cb:
        s += "}" * (ob - cb)
    if osq > csq:
        s += "]" * (osq - csq)

    # Final pass: drop any newly-exposed trailing commas
    s = _drop_trailing_commas(s)

    # Heuristic cleanup: if a stray '}' ended up inside a string value right
    # before the terminal quote and final closer, drop it. This is a common
    # artifact when a model prematurely emits a closing brace before finishing
    # the string contents.
    s = re.sub(r"\}\s*\"\s*\}\s*$", r'"}', s)

    return s



def create(provider_name: str, *, params: Optional[object] = None, **kwargs):
    """Instantiate a provider adapter via ``ProviderFactory`` when available.

    Summary:
        Constructs and returns a concrete provider adapter instance identified
        by ``provider_name``. If the factory layer is not present in the
        current build, a :class:`ProviderError` is raised. This preserves the
        lightweight import path ``from crux_providers import create``.

    Parameters
    ----------
    provider_name:
        Canonical provider name (for example, ``"openai"``).
    params:
        Optional typed parameter object (``AdapterParams``) carrying common
        adapter initialization fields. Passed to the factory. Callers may
        continue to use ``**kwargs`` for backward compatibility.
    **kwargs:
        Legacy adapter constructor keyword arguments. When both ``params`` and
        ``kwargs`` provide the same field, ``kwargs`` take precedence.

    Returns
    -------
    object
        A provider adapter instance implementing the appropriate interfaces
        for the requested provider.

    Raises
    ------
    ProviderError
        If the factory is not available or if an error occurs during
        instantiation.
    """
    if ProviderFactory is None:  # type: ignore
        raise ProviderError(code=ErrorCode.UNKNOWN, message="ProviderFactory not available in this build", provider="unknown")
    try:
        # Pass typed params to the factory for coercion; kwargs remain supported.
        return ProviderFactory.create(provider_name, params=params, **kwargs)  # type: ignore[attr-defined]
    except Exception as e:  # Wrap in unified error type
        raise ProviderError(code=ErrorCode.UNKNOWN, message=f"Failed to create provider '{provider_name}': {e}", provider=provider_name) from e


def load_plugin(entry_point_name: str):  # pragma: no cover - future extension
    """Load a plugin registered under the ``crux_providers.plugins`` entry point group.

    Example (pyproject.toml):
        [project.entry-points."crux_providers.plugins"]
        my_custom = "my_pkg.custom_provider:CustomProvider"

    Parameters:
        entry_point_name: The plugin name registered under the
            ``crux_providers.plugins`` entry point group.

    Returns:
        The loaded object exported by the matched entry point.

    Raises:
        LookupError: If no plugin matching ``entry_point_name`` is registered.
    """
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover
        import importlib_metadata as metadata  # type: ignore

    eps = metadata.entry_points()
    group = eps.select(group="crux_providers.plugins") if hasattr(eps, "select") else eps.get("crux_providers.plugins", [])
    for ep in group:
        if ep.name == entry_point_name:
            return ep.load()
    raise LookupError(f"No provider plugin named '{entry_point_name}'")
