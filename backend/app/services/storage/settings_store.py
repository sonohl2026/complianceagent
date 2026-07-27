"""Database-backed store for mutable runtime settings.

Runtime settings (OpenRouter/Brave API keys, model slugs, privacy toggles)
live in a single-row `runtime_settings` table rather than a local file
(see migration 0013): a host like Render's free tier has no persistent disk
across restarts/redeploys, so a file would silently reset to defaults --
losing the configured API keys -- on every deploy. Deliberately synchronous
(a small dedicated engine, not the app's async one) so none of this
function's existing call sites need to change to async/await.
"""

import json
from typing import Any

from sqlalchemy import create_engine, text

from app.config import get_settings

DEFAULTS: dict[str, Any] = {
    "openrouter_api_key": "",
    # Name-only submission fallback (see quick_scan/pipeline.py's
    # run_quick_scan_identity_resolution): only ever queried when openFDA/CMS
    # retrieval on the typed name comes back with zero hits, to find a
    # candidate site the user can confirm before it's fetched and analyzed.
    "brave_search_api_key": "",
    "openrouter_model": "",
    "openrouter_extraction_model": "",
    "openrouter_synthesis_model": "",
    "openrouter_citation_model": "",
    "openrouter_zdr": True,
    "openrouter_prompt_caching": True,
    "allowed_model_slugs": [],
    "redact_emails": True,
    "redact_phone_numbers": True,
    "redact_patient_identifiers": True,
    "exclude_restricted_documents": True,
    "allow_ocr": False,
    "allow_lan_access": False,
    # quick_scan pipeline: CMS Coverage API's licensed LCD/Article-detail
    # endpoints are gated behind this flag. Flipping it on IS the user's own
    # acceptance of the AMA CPT / ADA CDT / AHA UB-04 license agreements --
    # this app never calls CMS's license-agreement endpoint on its own.
    "cms_license_accepted": False,
    # UI-side gate (v2 spec, section 5): even if a licensed CMS response ever
    # contained a full CPT descriptor, the dashboard only shows the code
    # number + a short paraphrase + an official-lookup link unless this is
    # explicitly enabled.
    "cpt_license": False,
}

_ROW_ID = 1


def _sync_engine():
    # settings.database_url is already the sync psycopg (v3) dialect
    # ("postgresql+psycopg://...") -- app/database.py rewrites it to
    # asyncpg for the app's own async engine; this one deliberately stays
    # sync, a short-lived connection per call rather than a pooled engine
    # (this is called from both the FastAPI process and every Celery task's
    # own fresh event loop/process, so there's no single long-lived pool to
    # share anyway).
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def load_runtime_settings() -> dict[str, Any]:
    engine = _sync_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT data FROM runtime_settings WHERE id = :id"), {"id": _ROW_ID}).first()
    except Exception:  # noqa: BLE001 - a DB hiccup here must never crash a request; fall back to defaults
        return dict(DEFAULTS)
    finally:
        engine.dispose()

    merged = dict(DEFAULTS)
    if row is not None and row[0]:
        merged.update(row[0])
    return merged


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_runtime_settings()
    current.update({k: v for k, v in updates.items() if v is not None})

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO runtime_settings (id, data, updated_at) VALUES (:id, CAST(:data AS JSONB), now()) "
                    "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()"
                ),
                {"id": _ROW_ID, "data": json.dumps(current)},
            )
    finally:
        engine.dispose()
    return current


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"
