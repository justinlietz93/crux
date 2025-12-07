"""Model catalog loader for seeding the SQLite-backed model registry from YAML.

This module lives in the *service* layer and is responsible for reading
provider-centric YAML catalog files from ``crux_providers/catalog/providers``
and materializing them into the authoritative SQLite ``model_registry`` tables
via the model registry repository.

YAML Schema (per-provider)
-------------------------

Each catalog file is a single-provider document with the following shape:

.. code-block:: yaml

    provider: openai
    display_name: OpenAI
    aliases:
      - openai
    metadata:
      tier: production
    models:
      - id: gpt-4o
        name: gpt-4o
        family: gpt-4o
        context_length: 128000
        updated_at: null
        capabilities:
          # Void-oriented capabilities; stored as-is in the DB and later
          # merged with observed/provider data by `apply_void_enrichment`.
          context_window: 128000
          reserved_output_token_space: 16384
          system_message: system-role
          tool_format: openai
          fim: false
          reasoning:
            supports_reasoning: false
          pricing:
            input_per_1k_tokens_usd: 2.5
            output_per_1k_tokens_usd: 10.0

Only ``provider`` and ``models`` are strictly required. All other keys are
treated as metadata and preserved for future `/api/providers` and `/api/models`
surfaces.

Persistence Path
----------------

This loader does **not** talk to SQLite directly. Instead it:

1. Parses YAML into :class:`ModelInfo` instances.
2. Wraps them in a :class:`ModelRegistrySnapshot`.
3. Persists via :class:`ModelRegistryRepository`, which in turn writes
   to the SQLite-backed ``model_registry`` tables.

This keeps the service layer aligned with the repository abstraction and avoids
introducing a second persistence path.

"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:  # Import-time guard; keeps dependency explicit and localized.
    import yaml
except Exception as exc:  # pragma: no cover - import-time guard
    raise RuntimeError(
        "PyYAML is required to use the Crux model catalog loader. "
        "Install the 'pyyaml' package in the Crux runtime environment."
    ) from exc

from ..base.models_parts.model_info import ModelInfo
from ..base.models_parts.model_registry_snapshot import ModelRegistrySnapshot
from ..base.repositories.model_registry.repository import ModelRegistryRepository


def _default_catalog_root() -> Path:
    """Return the default catalog root (``crux_providers/catalog/providers``).

    The path is computed relative to this file to avoid reliance on the
    working directory or import side effects.
    """
    # <repo>/crux/crux_providers/service/model_catalog_loader.py
    # parents[0] - service/
    # parents[1] - crux_providers/
    return Path(__file__).resolve().parents[1] / "catalog" / "providers"


def _coerce_context_length(val: Any) -> Optional[int]:
    """Coerce a context length value into an integer when possible.

    The catalog is expected to use plain integers for ``context_length``,
    but this helper is defensive against accidental string values.

    Returns
    -------
    Optional[int]
        Parsed integer value, or ``None`` on failure/absence.
    """
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _coerce_capabilities(raw: Any) -> Dict[str, Any]:
    """Normalize capabilities payload into a dict.

    This mirrors the behavior in the SQLite store in a simplified way:
    - ``dict`` instances are passed through unchanged.
    - ``None`` becomes ``{}``.
    - Any other value is wrapped under ``{"raw_capabilities": raw}``.
    """
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    return {"raw_capabilities": raw}


def _load_yaml_document(path: Path) -> Dict[str, Any]:
    """Load and validate a single YAML catalog document.

    Parameters
    ----------
    path:
        Path to the provider catalog YAML file.

    Returns
    -------
    Dict[str, Any]
        Parsed top-level mapping.

    Raises
    ------
    ValueError
        If the root of the YAML document is not a mapping.
    """
    text = path.read_text(encoding="utf-8")
    data: Any = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Catalog file {path} must contain a mapping at top level.")
    return data


def _normalize_provider_id(doc: Dict[str, Any], path: Path) -> str:
    """Derive a normalized provider identifier from a catalog document.

    Priority:
    1. Explicit ``provider`` field.
    2. File stem (e.g., ``openai`` from ``openai.yaml``).

    The returned identifier is lowercased and stripped.
    """
    raw = doc.get("provider") or path.stem
    return str(raw).lower().strip()


def _metadata_from_document(doc: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """Build metadata payload for :class:`ModelRegistrySnapshot`.

    The loader preserves any explicit ``metadata`` block from the YAML and
    adds lightweight enrichment for provider and catalog provenance.
    """
    base_meta: Dict[str, Any] = {}
    raw_meta = doc.get("metadata")
    if isinstance(raw_meta, dict):
        base_meta.update(raw_meta)

    # Non-destructive enrichment
    display_name = doc.get("display_name")
    if display_name is not None and "display_name" not in base_meta:
        base_meta["display_name"] = display_name

    aliases = doc.get("aliases")
    if aliases and "aliases" not in base_meta:
        base_meta["aliases"] = aliases

    base_meta.setdefault("source", "catalog")
    base_meta.setdefault("catalog_file", str(path))

    return base_meta


def _model_from_entry(provider: str, entry: Dict[str, Any]) -> ModelInfo:
    """Convert a single catalog model entry into :class:`ModelInfo`.

    The field mapping intentionally mirrors the SQLite registry schema:

    - ``id``           -> ``model_id`` in DB
    - ``name``         -> display name
    - ``family``       -> optional family/category
    - ``context_length`` -> integer context window, when provided
    - ``capabilities`` -> JSON-encoded capability blob
    - ``updated_at``   -> optional ISO timestamp
    """
    mid = str(entry.get("id") or entry.get("model") or entry.get("name") or "unknown")
    name = str(entry.get("name") or entry.get("id") or mid)
    family_raw = entry.get("family")
    family = family_raw if isinstance(family_raw, str) else None
    ctx = _coerce_context_length(entry.get("context_length"))
    caps = _coerce_capabilities(entry.get("capabilities"))
    updated_raw = entry.get("updated_at")
    updated_at = updated_raw if isinstance(updated_raw, str) else None

    return ModelInfo(
        id=mid,
        name=name,
        provider=provider,
        family=family,
        context_length=ctx,
        capabilities=caps,
        updated_at=updated_at,
    )


def discover_catalog_files(root: Optional[Path] = None) -> List[Path]:
    """Return all provider catalog YAML files under the catalog root.

    Parameters
    ----------
    root:
        Optional explicit catalog root. When omitted, defaults to
        ``crux_providers/catalog/providers`` relative to this module.

    Returns
    -------
    List[Path]
        Sorted list of existing ``*.yaml`` files. Missing roots yield an
        empty list.
    """
    base = root or _default_catalog_root()
    if not base.exists():
        return []
    return sorted(p for p in base.glob("*.yaml") if p.is_file())


def load_model_catalog(
    *,
    catalog_root: Optional[Path] = None,
    repository: Optional[ModelRegistryRepository] = None,
) -> None:
    """Load all YAML provider catalogs into the SQLite model registry.

    This function is idempotent per provider: each invocation overwrites the
    existing snapshot for that provider in the registry with the contents of
    the corresponding YAML document.

    Parameters
    ----------
    catalog_root:
        Optional explicit catalog root. If omitted, the loader uses the
        standard ``crux_providers/catalog/providers`` directory.
    repository:
        Optional pre-configured :class:`ModelRegistryRepository` instance.
        When omitted, a default repository is constructed.

    Notes
    -----
    - Empty or model-less documents are ignored.
    - Per-provider fetch provenance defaults to ``"catalog"`` for
      ``fetched_via`` unless explicitly overridden in the YAML.
    """
    repo = repository or ModelRegistryRepository()
    files = discover_catalog_files(catalog_root)
    if not files:
        return

    for path in files:
        doc = _load_yaml_document(path)
        provider = _normalize_provider_id(doc, path)
        raw_models: Any = doc.get("models") or []
        if not isinstance(raw_models, list):
            # Defensive: mis-shaped documents should fail loudly.
            raise ValueError(
                f"Catalog file {path} must define 'models' as a list; "
                f"got {type(raw_models)!r} instead."
            )

        models: List[ModelInfo] = []
        for item in raw_models:
            if not isinstance(item, dict):
                # Ignore malformed entries rather than failing the entire provider.
                continue
            models.append(_model_from_entry(provider, item))

        if not models:
            # Nothing to persist for this provider.
            continue

        fetched_via = str(doc.get("fetched_via") or "catalog")
        fetched_at_raw = doc.get("fetched_at")
        fetched_at = str(fetched_at_raw) if fetched_at_raw is not None else None
        metadata = _metadata_from_document(doc, path)

        snapshot = ModelRegistrySnapshot(
            provider=provider,
            models=models,
            fetched_via=fetched_via,
            fetched_at=fetched_at,
            metadata=metadata,
        )
        repo.save_snapshot(snapshot)


__all__ = [
    "discover_catalog_files",
    "load_model_catalog",
]