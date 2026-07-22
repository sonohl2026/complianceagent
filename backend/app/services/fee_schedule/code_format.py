"""Classifies a code's format to decide whether its description is safe to
display (spec: never reproduce a full AMA CPT descriptor). Confirmed by
downloading and reading a real CMS PFS Relative Value file: its own header
states "CPT codes and descriptions only are copyright ... American Medical
Association" -- that applies to 5-digit numeric codes (Category I) and
4-digit+letter codes (Category II/III, e.g. 0001T performance-measure or
temporary codes). HCPCS Level II codes (letter+4-digit, e.g. A4238) are
CMS's own creation, public domain, no AMA license involved."""

import re

from app.services.fee_schedule.types import CodeFormat

_CPT_CATEGORY_I = re.compile(r"^\d{5}$")
_CPT_CATEGORY_II_III = re.compile(r"^\d{4}[A-Z]$")
_HCPCS_LEVEL_II = re.compile(r"^[A-Z]\d{4}$")


def classify_code_format(code: str) -> CodeFormat:
    code = code.strip().upper()
    if _CPT_CATEGORY_I.match(code):
        return CodeFormat.CPT_CATEGORY_I
    if _CPT_CATEGORY_II_III.match(code):
        return CodeFormat.CPT_CATEGORY_II_III
    if _HCPCS_LEVEL_II.match(code):
        return CodeFormat.HCPCS_LEVEL_II
    return CodeFormat.UNKNOWN


def is_ama_licensed_format(code_format: CodeFormat) -> bool:
    return code_format in (CodeFormat.CPT_CATEGORY_I, CodeFormat.CPT_CATEGORY_II_III)
