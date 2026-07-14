from app.services.llm.redaction import (
    apply_redaction,
    redact_emails,
    redact_patient_identifiers,
    redact_phone_numbers,
)


def test_redact_emails_replaces_address():
    assert redact_emails("Contact info@sonohl.com for details") == "Contact [REDACTED-EMAIL] for details"


def test_redact_emails_leaves_plain_text_alone():
    assert redact_emails("No email here.") == "No email here."


def test_redact_phone_numbers_common_formats():
    for phone in ["(555) 123-4567", "555-123-4567", "555.123.4567", "+1 555 123 4567"]:
        assert "[REDACTED-PHONE]" in redact_phone_numbers(f"Call {phone} now")


def test_redact_patient_identifiers_ssn_shape():
    assert redact_patient_identifiers("SSN 123-45-6789 on file") == "SSN [REDACTED-ID] on file"


def test_redact_patient_identifiers_mrn_label():
    assert "[REDACTED-ID]" in redact_patient_identifiers("MRN: 00123456 confirmed")


def test_apply_redaction_respects_disabled_toggles():
    text = "Email info@sonohl.com or call 555-123-4567"
    result = apply_redaction(
        text, redact_emails_enabled=True, redact_phones_enabled=False, redact_patient_ids_enabled=False
    )
    assert "[REDACTED-EMAIL]" in result
    assert "555-123-4567" in result


def test_apply_redaction_all_disabled_is_a_no_op():
    text = "info@sonohl.com 555-123-4567 123-45-6789"
    result = apply_redaction(
        text, redact_emails_enabled=False, redact_phones_enabled=False, redact_patient_ids_enabled=False
    )
    assert result == text
