"""Typed parameter object for provider adapter initialization.

Purpose
-------
Provide a small, provider-agnostic DTO that captures common initialization
parameters used across adapters. This reduces long argument lists, promotes a
stable contract at the boundary (factory/DI), and supports forward-compatible
extension by carrying an ``extra`` bag for provider-specific fields.

External dependencies
---------------------
- Pydantic v2 ``BaseModel`` for validation and `.model_dump()` convenience.

Failure modes & side effects
----------------------------
- Pure data container: no I/O side effects. Validation errors may be raised by
  Pydantic if inputs are of incorrect types.

Notes
-----
- Timeouts should be handled by higher-level timeout policies; this DTO merely
  transports configuration values.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, Field


class AdapterParams(BaseModel):
    """Common provider adapter initialization parameters.

    Attributes
    ----------
    provider:
        Canonical provider name (e.g., ``"openai"``, ``"gemini"``). Optional to
        keep compatibility with call sites that already specify the provider
        separately.
    model:
        Default model identifier to use for operations when the adapter allows
        setting a default.
    api_key:
        API key or token string if the adapter supports direct credential
        passing. Prefer secure key management; this field exists for explicit
        wiring.
    base_url:
        Optional override for API base URL (useful for proxies or self-hosted
        gateways).
    organization:
        Optional organization/tenant hint used by some providers.
    timeout_seconds:
        Optional request timeout hint; actual timeout enforcement should rely on
        central timeout configuration. This value is advisory.
    headers:
        Optional static HTTP header mapping to add to requests.
    extra:
        Free-form provider-specific configuration bag. Keys should be
        well-documented at the call site.
    """

    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    timeout_seconds: Optional[float] = None
    headers: Mapping[str, str] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["AdapterParams"]
