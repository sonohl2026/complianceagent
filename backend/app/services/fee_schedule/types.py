"""Shared vocabulary for the CMS fee-schedule lookup (closes the coding/
payment pillar gap -- see plan doc for the full "device -> candidate code ->
verify against real data" design)."""

import enum
from dataclasses import dataclass


class CodeFormat(str, enum.Enum):
    CPT_CATEGORY_I = "CPT_CATEGORY_I"  # 5 digits, e.g. 76705 -- AMA copyright
    CPT_CATEGORY_II_III = "CPT_CATEGORY_II_III"  # 4 digits + letter, e.g. 0001T -- AMA copyright
    HCPCS_LEVEL_II = "HCPCS_LEVEL_II"  # letter + 4 digits, e.g. A4238 -- public domain, CMS's own
    UNKNOWN = "UNKNOWN"


@dataclass
class FeeScheduleEntry:
    code: str
    code_format: CodeFormat
    active: bool
    source: str  # "pfs" | "dmepos"
    payment_system: str  # "PFS" | "DMEPOS"
    rate_usd: float | None  # None when the code exists but isn't separately priced (e.g. bundled/status "B")
    status_code: str | None
    # Only ever populated for HCPCS_LEVEL_II (public domain). CPT-format
    # codes' descriptions are AMA-copyrighted even in CMS's own public
    # files (confirmed by reading the real PPRRVU file's own header) --
    # never populated for those, enforced at parse time, not left to a
    # caller to remember.
    description: str | None
