"""Physician Fee Schedule Relative Value File ingestion.

No queryable API exists for this (re-confirmed live against data.cms.gov's
DCAT catalog -- no RVU/PFS dataset) -- CMS only publishes it as a quarterly
bulk zip. Verified live (see plan doc): the index page at
cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files
links to one subpage per quarter (rvu{YY}{a-d}), each of which links to the
actual zip (confirmed real: rvu26c-updated-06-30-2026.zip, ~6MB, containing
PPRRVU{YYYY}_{Mon}_nonQPP.csv among other files).

Parses the PPRRVU csv's real, confirmed layout (downloaded and inspected a
real file to get this, not assumed from memory): a few title/copyright
lines, then a two-physical-line wrapped header, then data rows. The header
text itself changes wording between releases, so this locates the header
by its first cell being exactly "HCPCS" rather than a fixed line number,
but the DATA row's column *positions* are fixed-index (verified against
multiple real rows: code=0, modifier=1, description=2, status=3, work
RVU=5, non-facility total RVU=11, facility total RVU=12, conversion
factor=25) -- re-verify these positions if CMS ever changes the file
layout, the same "time-sensitive external format" discipline already
applied elsewhere in this codebase (OpenRouter/CMS Coverage/openFDA).

Rate calculation here is deliberately simple for v1: national non-facility
total RVU * conversion factor, with no GPCI geographic adjustment (that
file exists too -- GPCI{YYYY}.csv, in the same zip -- and is a reasonable
follow-up if locality-specific rates matter later). Good enough for an
informational "does this code exist and roughly what does it pay" pillar
finding, not a billing-accurate rate.

Also returns a SEPARATE raw-description index (code -> the file's own short
description, for every code regardless of CPT/HCPCS format) alongside the
normal entries. This is for app/services/fee_schedule/description_search.py
and app/services/quick_scan/code_candidates.py's internal candidate-code
search ONLY -- never merged into FeeScheduleEntry.description (which stays
None for CPT-format codes, per the AMA-license rule enforced in
code_format.py). Caller is responsible for keeping this index out of
anything that reaches Stage 3's evidence bundle or the UI.
"""

import csv
import io
import re
import zipfile

import httpx

from app.services.fee_schedule.code_format import classify_code_format, is_ama_licensed_format
from app.services.fee_schedule.types import FeeScheduleEntry

_INDEX_URL = "https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files"
_QUARTER_LINK_RE = re.compile(r'href="(/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu(\d{2})([a-d]))"')
_ZIP_LINK_RE = re.compile(r'href="(/files/zip/[^"]+\.zip)"')
_TIMEOUT_SECONDS = 30.0

_ACTIVE_STATUS_CODES = {"A", "R"}  # active/payable, restricted-active


async def find_current_release_zip_url(client: httpx.AsyncClient) -> str | None:
    """Finds the most recent quarter's zip by reading CMS's own index page
    live, rather than guessing a URL pattern -- CMS's naming has drifted
    across years (medicare-fee-service-payment/... vs medicare/payment/...
    path prefixes both appear in current links), so constructing a URL from
    a remembered template is not reliable."""
    response = await client.get(_INDEX_URL, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
    if response.status_code != 200:
        return None
    quarters = _QUARTER_LINK_RE.findall(response.text)
    if not quarters:
        return None
    # (year, quarter_letter) sorts correctly since a<b<c<d matches Jan<Apr<Jul<Oct
    quarters.sort(key=lambda q: (q[1], q[2]), reverse=True)
    latest_path = quarters[0][0]

    quarter_response = await client.get(f"https://www.cms.gov{latest_path}", timeout=_TIMEOUT_SECONDS, follow_redirects=True)
    if quarter_response.status_code != 200:
        return None
    zip_matches = _ZIP_LINK_RE.findall(quarter_response.text)
    if not zip_matches:
        return None
    return f"https://www.cms.gov{zip_matches[0]}"


def _find_nonqpp_csv_name(names: list[str]) -> str | None:
    candidates = [n for n in names if n.upper().startswith("PPRRVU") and n.lower().endswith(".csv") and "nonqpp" in n.lower()]
    return candidates[0] if candidates else None


def parse_pprrvu_csv(content: bytes) -> tuple[dict[str, FeeScheduleEntry], dict[str, str]]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    header_index = next((i for i, row in enumerate(rows) if row and row[0].strip() == "HCPCS"), None)
    if header_index is None:
        raise ValueError("PPRRVU file layout not recognized -- no row starting with 'HCPCS' found")

    entries: dict[str, FeeScheduleEntry] = {}
    raw_descriptions: dict[str, str] = {}
    for row in rows[header_index + 1:]:
        if len(row) < 26 or not row[0].strip():
            continue
        code = row[0].strip()
        modifier = row[1].strip()
        if code in entries and modifier:
            continue  # keep the unmodified (blank-modifier) row when one exists

        status = row[3].strip()
        code_format = classify_code_format(code)
        active = status in _ACTIVE_STATUS_CODES
        rate_usd = None
        try:
            non_facility_total = float(row[11])
            conversion_factor = float(row[25])
            if active and non_facility_total > 0:
                rate_usd = round(non_facility_total * conversion_factor, 2)
        except (ValueError, IndexError):
            pass

        raw_description = row[2].strip()
        if raw_description:
            raw_descriptions[code] = raw_description
        description = None if is_ama_licensed_format(code_format) else (raw_description or None)
        entries[code] = FeeScheduleEntry(
            code=code, code_format=code_format, active=active, source="pfs",
            payment_system="PFS", rate_usd=rate_usd, status_code=status or None, description=description,
        )
    return entries, raw_descriptions


async def download_and_parse(client: httpx.AsyncClient) -> tuple[dict[str, FeeScheduleEntry], dict[str, str]] | None:
    zip_url = await find_current_release_zip_url(client)
    if zip_url is None:
        return None
    response = await client.get(zip_url, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
    if response.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        csv_name = _find_nonqpp_csv_name(archive.namelist())
        if csv_name is None:
            return None
        content = archive.read(csv_name)
    return parse_pprrvu_csv(content)
