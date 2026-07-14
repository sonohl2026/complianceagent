import pytest

from app.services.parsing.validation import UploadValidationError, validate_upload
from app.services.storage.file_storage import sanitize_filename


def test_sanitize_filename_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/absolute/path/report.pdf") == "report.pdf"


def test_sanitize_filename_collapses_unsafe_characters():
    assert sanitize_filename("weird name!@#.txt") == "weird_name_.txt"


def test_sanitize_filename_handles_empty_result():
    assert sanitize_filename("...") == "unnamed"


def test_validate_upload_accepts_real_pdf_magic_bytes():
    content = b"%PDF-1.4\n%mock pdf content"
    result = validate_upload("report.pdf", content)
    assert result.extension == ".pdf"
    assert result.mime_type == "application/pdf"


def test_validate_upload_rejects_extension_content_mismatch():
    with pytest.raises(UploadValidationError):
        validate_upload("fake.pdf", b"this is not a pdf")


def test_validate_upload_rejects_unsupported_extension():
    with pytest.raises(UploadValidationError):
        validate_upload("archive.zip", b"PK\x03\x04fake zip")


def test_validate_upload_rejects_executable_disguised_as_text():
    with pytest.raises(UploadValidationError):
        validate_upload("notes.txt", b"MZ\x90\x00\x03executable-looking-bytes")


def test_validate_upload_rejects_double_extension_trick():
    # "report.pdf.exe" -- a classic attempt to slip an executable past a
    # naive "ends with an allowed extension" check. _extension_of only
    # matches a *true* suffix against the allow-list, so ".exe" (not in the
    # allow-list) means this is rejected as unsupported, not silently
    # treated as a PDF.
    with pytest.raises(UploadValidationError):
        validate_upload("report.pdf.exe", b"MZ\x90\x00\x03executable-looking-bytes")


def test_validate_upload_double_extension_ending_in_allowed_type_is_still_content_checked():
    # "malware.exe.pdf" ends in an allowed extension, so it's accepted as a
    # PDF *only if the actual bytes are a real PDF* -- the extension alone
    # never overrides the magic-byte check.
    with pytest.raises(UploadValidationError):
        validate_upload("malware.exe.pdf", b"MZ\x90\x00\x03this is an exe, not a pdf")


def test_validate_upload_rejects_oversized_file(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    get_settings.cache_clear()
    try:
        with pytest.raises(UploadValidationError):
            validate_upload("notes.txt", b"hello world")
    finally:
        monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
        get_settings.cache_clear()


def test_validate_upload_accepts_plain_text():
    result = validate_upload("notes.txt", "Hello, SonoHL.".encode())
    assert result.extension == ".txt"


def test_validate_upload_accepts_ooxml_docx():
    result = validate_upload("spec.docx", b"PK\x03\x04" + b"0" * 40)
    assert result.extension == ".docx"
