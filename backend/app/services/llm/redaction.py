"""Best-effort redaction applied to retrieved chunk text before it leaves the
host for OpenRouter, gated by the Settings privacy toggles (build spec §9.4).

Regex-based redaction is inherently incomplete (it cannot catch every way a
phone number or name might be written) -- this reduces exposure, it does not
guarantee removal. The Settings notice already tells users not to submit
PHI/PII regardless of these toggles; this is defense in depth, not a
substitute for that judgment.
"""

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
)
# Heuristic "likely patient identifier" patterns: SSN-shaped and MRN-labeled numbers.
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_MRN_RE = re.compile(r"\b(?:MRN|Medical Record Number)\s*[:#]?\s*\d{4,12}\b", re.IGNORECASE)


def redact_emails(text: str) -> str:
    return _EMAIL_RE.sub("[REDACTED-EMAIL]", text)


def redact_phone_numbers(text: str) -> str:
    return _PHONE_RE.sub("[REDACTED-PHONE]", text)


def redact_patient_identifiers(text: str) -> str:
    text = _SSN_RE.sub("[REDACTED-ID]", text)
    text = _MRN_RE.sub("[REDACTED-ID]", text)
    return text


def apply_redaction(
    text: str,
    *,
    redact_emails_enabled: bool,
    redact_phones_enabled: bool,
    redact_patient_ids_enabled: bool,
) -> str:
    if redact_emails_enabled:
        text = redact_emails(text)
    if redact_phones_enabled:
        text = redact_phone_numbers(text)
    if redact_patient_ids_enabled:
        text = redact_patient_identifiers(text)
    return text
