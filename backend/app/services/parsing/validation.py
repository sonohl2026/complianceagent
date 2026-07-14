"""Upload validation: size, content-sniffed MIME type, and executable rejection.

Never trust the client-supplied filename extension or Content-Type header
alone — this module sniffs magic bytes and cross-checks against what the
filename claims to be, per build spec §11 and §20.3 ("Upload security").
"""

from dataclasses import dataclass

from app.config import get_settings

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
}

_EXECUTABLE_MAGIC = (
    b"MZ",  # Windows PE
    b"\x7fELF",  # Linux ELF
    b"\xca\xfe\xba\xbe",  # Mach-O / Java class (fat binary)
    b"\xfe\xed\xfa",  # Mach-O
)


class UploadValidationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class ValidatedUpload:
    extension: str
    mime_type: str
    size_bytes: int


def _extension_of(filename: str) -> str:
    lower = filename.lower()
    for ext in EXTENSION_TO_MIME:
        if lower.endswith(ext):
            return ext
    return ""


def _looks_like_zip_ooxml(content: bytes) -> bool:
    return content[:4] == b"PK\x03\x04"


def _looks_like_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def _looks_like_html(content: bytes) -> bool:
    head = content[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head" in head[:200]


def validate_upload(filename: str, content: bytes) -> ValidatedUpload:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise UploadValidationError(f"File exceeds MAX_UPLOAD_MB={settings.max_upload_mb}")
    if len(content) == 0:
        raise UploadValidationError("File is empty")

    for magic in _EXECUTABLE_MAGIC:
        if content[: len(magic)] == magic:
            raise UploadValidationError("Executable file signatures are not allowed")

    extension = _extension_of(filename)
    if not extension:
        raise UploadValidationError(
            f"Unsupported file type for {filename!r}; allowed: {sorted(EXTENSION_TO_MIME)}"
        )

    claimed_mime = EXTENSION_TO_MIME[extension]

    if extension == ".pdf" and not _looks_like_pdf(content):
        raise UploadValidationError("File extension is .pdf but content is not a PDF")
    if extension in (".docx", ".pptx", ".xlsx") and not _looks_like_zip_ooxml(content):
        raise UploadValidationError(f"File extension is {extension} but content is not a valid OOXML zip")
    if extension in (".html", ".htm") and not (_looks_like_html(content) or _is_probably_text(content)):
        raise UploadValidationError("File extension is .html but content is not text/HTML")
    if extension in (".txt", ".md", ".csv") and not _is_probably_text(content):
        raise UploadValidationError(f"File extension is {extension} but content is not text")

    return ValidatedUpload(extension=extension, mime_type=claimed_mime, size_bytes=len(content))


def _is_probably_text(content: bytes) -> bool:
    sample = content[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    result = from_bytes(sample).best()
    return result is not None
