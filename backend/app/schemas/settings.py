from pydantic import BaseModel, Field


class AppSettingsPublic(BaseModel):
    """Settings as returned to the browser. Secrets are always masked."""

    openrouter_api_key_configured: bool
    openrouter_api_key_masked: str
    openrouter_model: str
    openrouter_extraction_model: str
    openrouter_synthesis_model: str
    openrouter_citation_model: str
    openrouter_zdr: bool
    openrouter_prompt_caching: bool
    allowed_model_slugs: list[str]
    redact_emails: bool
    redact_phone_numbers: bool
    redact_patient_identifiers: bool
    exclude_restricted_documents: bool
    allow_ocr: bool
    allow_lan_access: bool
    cms_license_accepted: bool
    cpt_license: bool
    local_data_notice: str = Field(
        default=(
            "This application is locally hosted, but model requests sent through "
            "OpenRouter are processed by external model providers. Do not submit "
            "protected health information, patient-identifiable information, "
            "confidential clinical-trial data, privileged legal advice, or other "
            "restricted information unless your organization has approved the "
            "relevant data-processing arrangements."
        )
    )


class AppSettingsUpdate(BaseModel):
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_extraction_model: str | None = None
    openrouter_synthesis_model: str | None = None
    openrouter_citation_model: str | None = None
    openrouter_zdr: bool | None = None
    openrouter_prompt_caching: bool | None = None
    allowed_model_slugs: list[str] | None = None
    redact_emails: bool | None = None
    redact_phone_numbers: bool | None = None
    redact_patient_identifiers: bool | None = None
    exclude_restricted_documents: bool | None = None
    allow_ocr: bool | None = None
    allow_lan_access: bool | None = None
    cms_license_accepted: bool | None = None
    cpt_license: bool | None = None
