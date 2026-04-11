"""listing.py — Bedrock model catalogue for bedrock-model-compare.

All core logic (pricing, size classification, model listing, filtering,
deduplication) now lives in the shared ``bedrock-tui-helpers`` package.
This module keeps only the restricted-IDs cache that is specific to this
project (persisted under ``results/`` so each install tracks its own
account-access errors independently).
"""

from __future__ import annotations

import json
import os

# Re-export everything the rest of the project imports from this module
# so no other file needs to change its import statements.
from bedrock_tui_helpers.models import (       # noqa: F401 (re-export)
    MODEL_PRICING,
    SIZE_ORDER,
    get_pricing,
    providers,
    sizes_summary,
    to_invoke_id,
)
import bedrock_tui_helpers.models as _tui
from bedrock_tui_helpers.probe import load_disabled_ids, ensure_probe  # noqa: F401 (re-export)

# ---------------------------------------------------------------------------
# Restricted-model cache (project-local — stored in results/)
# ---------------------------------------------------------------------------
_RESTRICTED_FILE = os.path.join(os.path.dirname(__file__), "results", ".restricted_ids.json")


def load_restricted_ids() -> set[str]:
    """Return the set of model IDs known to be restricted for this account."""
    try:
        with open(_RESTRICTED_FILE, encoding="utf-8") as fh:
            return set(json.load(fh))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_restricted_id(model_id: str) -> None:
    """Append *model_id* to the persistent restricted-model cache."""
    ids = load_restricted_ids()
    ids.add(model_id)
    os.makedirs(os.path.dirname(_RESTRICTED_FILE), exist_ok=True)
    with open(_RESTRICTED_FILE, "w", encoding="utf-8") as fh:
        json.dump(sorted(ids), fh, indent=2)


# ---------------------------------------------------------------------------
# list_models — wraps the shared implementation, injects restricted IDs
# ---------------------------------------------------------------------------

def list_models(force_refresh: bool = False) -> list[dict]:
    """Return all Bedrock foundation models, annotated with ``_size``, ``_in_price``,
    ``_out_price``, and ``_invoke_id``.

    Delegates caching and annotation to ``bedrock_tui_helpers.models.list_models``.
    """
    return _tui.list_models(force_refresh=force_refresh)


def filter_models(
    models: list[dict],
    *,
    provider: str | None = None,
    size: str | None = None,
    modality: str = "TEXT",
) -> list[dict]:
    """Filter *models*, automatically excluding restricted and disabled IDs.

    Disabled models are read from the shared probe cache in bedrock-tui-helpers
    (``probe.load_disabled_ids()``).  Run ``test_models.py`` or call
    ``bedrock_tui_helpers.ensure_probe()`` to refresh the cache.
    """
    restricted = load_restricted_ids() | load_disabled_ids()
    return _tui.filter_models(
        models,
        provider=provider,
        size=size,
        modality=modality,
        restricted_ids=restricted,
    )
