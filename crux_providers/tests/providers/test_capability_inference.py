from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from crux_providers.base.get_models_base import _infer_caps, _normalize_capabilities  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true

_assert = assert_true


def _expect_flags(actual: Dict[str, Any], expected_present: Iterable[str], label: str) -> None:
    """Validate that all expected flags are present & truthy and no unexpected capability (other than json_output) appears.

    Args:
        actual: Inferred capability dictionary.
        expected_present: Iterable of capability flag names expected to be True.
        label: Descriptive label for the test case used in error messages.
    """
    expected_set: Set[str] = set(expected_present)
    # json_output is always inferred for openai models; include if present.
    allowed_extras = {"json_output"}
    missing = [f for f in expected_set if not actual.get(f)]
    # Unexpected = any key (excluding allowed extras) that we did not ask for.
    unexpected = [k for k in actual if k not in expected_set and k not in allowed_extras and actual.get(k)]
    _assert(not missing, f"[{label}] Missing expected capability flags: {missing}; actual={actual}")
    _assert(not unexpected, f"[{label}] Unexpected capability flags inferred: {unexpected}; actual={actual}")


CASES = [
    ("openai", "o1-preview", {"reasoning", "responses_api"}),
    ("openai", "o3-mini", {"reasoning", "responses_api"}),
    ("openai", "gpt-4o-mini", {"vision"}),
    ("openai", "gpt-4o-vision-preview", {"vision"}),
    ("openai", "text-embedding-3-large", {"embedding"}),
    ("openai", "custom-embedding-alpha", {"embedding"}),
    ("openai", "gpt-search-alpha", {"search"}),
    ("openai", "legacy-model", set()),  # Only json_output baseline
]


def test_infer_caps_matrix() -> None:
    """Table-driven verification of `_infer_caps` across representative model ids."""
    for provider, model_id, expected in CASES:
        caps = _infer_caps(provider, model_id)
        _expect_flags(caps, expected, f"infer:{model_id}")
        if provider == "openai":
            _assert(caps.get("json_output") is True, f"[{model_id}] json_output should default to True for openai")
        else:
            _assert("json_output" not in caps, f"[{model_id}] Non-openai provider should not infer json_output")


def test_infer_caps_non_openai() -> None:
    """Non-OpenAI providers should yield an empty inference dictionary."""
    caps = _infer_caps("other", "some-model")
    _assert(caps == {}, f"Expected empty dict for non-openai provider, got {caps}")


def test_normalize_overrides_inference() -> None:
    """Explicit capability values must override inferred ones in merge order."""
    d = {"capabilities": {"reasoning": False}}
    merged = _normalize_capabilities(d, "openai", "o1-mini")
    _assert(merged.get("reasoning") is False, f"Explicit False should override inferred True: {merged}")
    _assert(merged.get("json_output") is True, "json_output baseline should still be present")


def test_modalities_enrichment_adds_vision() -> None:
    """Modalities containing 'image' or 'vision' should set the canonical 'vision' capability."""
    d = {"modalities": ["image"]}
    merged = _normalize_capabilities(d, "openai", "legacy-model")
    _assert(merged.get("vision") is True, f"vision should be inferred from modalities: {merged}")


def test_existing_caps_non_dict_wrapped() -> None:
    """Non-dict capabilities value should be preserved under 'raw_capabilities' key and merged with inference."""
    d = {"capabilities": ["raw", "tokens"]}
    merged = _normalize_capabilities(d, "openai", "gpt-4o-mini")
    _assert("raw_capabilities" in merged, f"raw_capabilities wrapper missing: {merged}")
    _assert(merged.get("vision") is True, f"vision should still be inferred for gpt-4o: {merged}")


def test_explicit_streaming_flag_preserved() -> None:
    """Explicit streaming flag should be preserved; not auto-inferred for non-matching model ids."""
    d = {"capabilities": {"streaming": True}}
    merged = _normalize_capabilities(d, "openai", "legacy-model")
    _assert(merged.get("streaming") is True, f"Explicit streaming flag lost: {merged}")
    # Ensure no unrelated capabilities inferred except json_output baseline
    unexpected = [k for k in merged if k not in {"streaming", "json_output"} and merged.get(k)]
    _assert(not unexpected, f"Unexpected inferred caps for legacy-model with explicit streaming: {unexpected}")


def test_no_streaming_inference_by_default() -> None:
    """Models without explicit streaming flag should not gain it implicitly."""
    merged = _normalize_capabilities({}, "openai", "legacy-model")
    _assert("streaming" not in merged, f"Streaming should not be inferred: {merged}")


def test_existing_listing_and_default_flags_preserved() -> None:
    """Arbitrary user-provided flags like 'listing' and 'default' must pass through untouched."""
    d = {"capabilities": {"listing": True, "default": True}}
    merged = _normalize_capabilities(d, "openai", "legacy-model")
    _assert(merged.get("listing") is True, f"listing flag missing: {merged}")
    _assert(merged.get("default") is True, f"default flag missing: {merged}")


def test_json_output_always_set_for_openai_even_with_other_flags() -> None:
    """json_output baseline should coexist with arbitrary explicit capability flags."""
    d = {"capabilities": {"listing": True}}
    merged = _normalize_capabilities(d, "openai", "gpt-search-alpha")
    _assert(merged.get("json_output") is True, f"json_output missing with explicit listing: {merged}")


def test_non_openai_no_json_output_baseline() -> None:
    """Non-openai models should not receive json_output or any inferred flags unless explicit."""
    d = {"capabilities": {"listing": True}}
    merged = _normalize_capabilities(d, "other", "some-model")
    _assert("json_output" not in merged, f"json_output incorrectly added for non-openai: {merged}")
    _assert(merged.get("listing") is True, f"Explicit listing lost for non-openai: {merged}")
