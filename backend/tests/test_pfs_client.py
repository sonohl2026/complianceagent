import httpx
import respx

from app.services.fee_schedule import pfs_client
from app.services.fee_schedule.types import CodeFormat

# Shaped exactly like a real PPRRVU csv (downloaded and inspected the real
# 2026 Q3 file to get this layout -- title/copyright lines, then a row
# whose first cell is literally "HCPCS" marking the real header, then data
# rows with fixed column positions: code=0, mod=1, description=2, status=3,
# work rvu=5, non-facility total=11, facility total=12, conv factor=25).
_SAMPLE_CSV = (
    ",,2026 National Physician Fee Schedule Relative Value File,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
    ",,CPT codes and descriptions only are copyright 2026 American Medical Association. All Rights Reserved.,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
    "HCPCS,MOD,DESCRIPTION,STATUS,X,WORK,PE,NA,PE,NA,MP,TOTAL,TOTAL,PCTC,GLOB,A,B,C,D,E,F,G,H,I,J,CONV,K,L,M,N,O,P\n"
    "76705,,Echo exam of abdomen,A,,0.58,1.96,,1.96,NA,0.04,2.58,2.58,1,XXX,0,0,0,4,0,0,0,0,9,,33.4009,09,0,88,3.39,3.39,0.05\n"
    "A4238,,Adju cgm supply allowance,X,,0.00,0.00,,0.00,,0.00,0.00,0.00,9,XXX,0,0,0,9,9,9,9,9,9,,33.4009,09,0,99,0.00,0.00,0.00\n"
    "00100,,Anes px salivary gland,J,,0.00,0.00,,0.00,,0.00,0.00,0.00,9,XXX,0,0,0,9,9,9,9,9,9,,33.4009,09,0,99,0.00,0.00,0.00\n"
    "77777,26,Split component row,A,,0.10,0.05,,0.05,,0.01,0.06,0.06,1,XXX,0,0,0,4,0,0,0,0,9,,33.4009,09,0,88,0.10,0.10,0.01\n"
    "77777,,Split component row global,A,,0.30,0.20,,0.20,,0.02,0.52,0.52,1,XXX,0,0,0,4,0,0,0,0,9,,33.4009,09,0,88,0.30,0.30,0.02\n"
)


def test_parses_active_cpt_code_with_rate_and_no_description():
    entries = pfs_client.parse_pprrvu_csv(_SAMPLE_CSV.encode())
    entry = entries["76705"]
    assert entry.code_format == CodeFormat.CPT_CATEGORY_I
    assert entry.active is True
    assert entry.rate_usd == round(2.58 * 33.4009, 2)
    assert entry.description is None  # AMA-licensed format -- never shown


def test_parses_hcpcs_level_ii_with_description_shown():
    entries = pfs_client.parse_pprrvu_csv(_SAMPLE_CSV.encode())
    entry = entries["A4238"]
    assert entry.code_format == CodeFormat.HCPCS_LEVEL_II
    assert entry.active is False  # status X: statutorily excluded from PFS
    assert entry.rate_usd is None
    assert entry.description == "Adju cgm supply allowance"  # public domain -- safe to show


def test_inactive_status_code_has_no_rate():
    entries = pfs_client.parse_pprrvu_csv(_SAMPLE_CSV.encode())
    entry = entries["00100"]
    assert entry.active is False
    assert entry.rate_usd is None


def test_prefers_unmodified_row_when_both_exist():
    # 77777 appears twice: once with modifier "26", once blank -- the blank
    # (global, unmodified) row should win regardless of file order.
    entries = pfs_client.parse_pprrvu_csv(_SAMPLE_CSV.encode())
    entry = entries["77777"]
    assert entry.rate_usd == round(0.52 * 33.4009, 2)


def test_unrecognized_layout_raises():
    import pytest
    with pytest.raises(ValueError):
        pfs_client.parse_pprrvu_csv(b"not,a,real,file\n1,2,3,4\n")


@respx.mock
async def test_find_current_release_zip_url_picks_latest_quarter():
    respx.get(pfs_client._INDEX_URL).mock(return_value=httpx.Response(200, text=(
        '<a href="/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25d">2025 Q4</a>'
        '<a href="/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26a">2026 Q1</a>'
        '<a href="/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c">2026 Q3</a>'
    )))
    respx.get("https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c").mock(
        return_value=httpx.Response(200, text='<a href="/files/zip/rvu26c-updated-06-30-2026.zip">Download</a>')
    )
    async with httpx.AsyncClient() as client:
        url = await pfs_client.find_current_release_zip_url(client)
    assert url == "https://www.cms.gov/files/zip/rvu26c-updated-06-30-2026.zip"


@respx.mock
async def test_find_current_release_zip_url_returns_none_on_404():
    respx.get(pfs_client._INDEX_URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        url = await pfs_client.find_current_release_zip_url(client)
    assert url is None
