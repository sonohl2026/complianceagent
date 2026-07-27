from fastapi import APIRouter

from app.schemas.settings import AppSettingsPublic, AppSettingsUpdate
from app.services.storage.settings_store import (
    load_runtime_settings,
    mask_secret,
    save_runtime_settings,
)

router = APIRouter()


def _to_public(data: dict) -> AppSettingsPublic:
    return AppSettingsPublic(
        openrouter_api_key_configured=bool(data.get("openrouter_api_key")),
        openrouter_api_key_masked=mask_secret(data.get("openrouter_api_key", "")),
        brave_search_api_key_configured=bool(data.get("brave_search_api_key")),
        brave_search_api_key_masked=mask_secret(data.get("brave_search_api_key", "")),
        openrouter_model=data.get("openrouter_model", ""),
        openrouter_extraction_model=data.get("openrouter_extraction_model", ""),
        openrouter_synthesis_model=data.get("openrouter_synthesis_model", ""),
        openrouter_citation_model=data.get("openrouter_citation_model", ""),
        openrouter_zdr=data.get("openrouter_zdr", True),
        openrouter_prompt_caching=data.get("openrouter_prompt_caching", True),
        allowed_model_slugs=data.get("allowed_model_slugs", []),
        redact_emails=data.get("redact_emails", True),
        redact_phone_numbers=data.get("redact_phone_numbers", True),
        redact_patient_identifiers=data.get("redact_patient_identifiers", True),
        exclude_restricted_documents=data.get("exclude_restricted_documents", True),
        allow_ocr=data.get("allow_ocr", False),
        allow_lan_access=data.get("allow_lan_access", False),
        cms_license_accepted=data.get("cms_license_accepted", False),
        cpt_license=data.get("cpt_license", False),
    )


@router.get("/settings", response_model=AppSettingsPublic)
async def get_settings_endpoint() -> AppSettingsPublic:
    return _to_public(load_runtime_settings())


@router.put("/settings", response_model=AppSettingsPublic)
async def update_settings_endpoint(update: AppSettingsUpdate) -> AppSettingsPublic:
    data = save_runtime_settings(update.model_dump(exclude_unset=True))
    return _to_public(data)
