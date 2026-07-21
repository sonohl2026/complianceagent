"""File-backed store for mutable runtime settings.

Runtime settings (OpenRouter key, model slugs, privacy toggles) are kept as a
local JSON file under the storage root rather than in the database, so that a
fresh checkout with no migrations applied can still boot and accept a key
through the UI. This is intentionally simple: it is a single local file, never
transmitted anywhere, and never rendered back to the browser un-redacted.
"""

import json
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

_lock = threading.Lock()

DEFAULTS: dict[str, Any] = {
    "openrouter_api_key": "",
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


def _settings_file() -> Path:
    settings = get_settings()
    config_dir = settings.storage_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "app_settings.json"


def load_runtime_settings() -> dict[str, Any]:
    path = _settings_file()
    if not path.exists():
        return dict(DEFAULTS)
    with _lock:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_runtime_settings()
    current.update({k: v for k, v in updates.items() if v is not None})
    path = _settings_file()
    with _lock:
        path.write_text(json.dumps(current, indent=2))
    return current


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"
