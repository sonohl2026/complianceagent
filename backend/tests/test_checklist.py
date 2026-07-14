import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import ComplianceIssueStatus, FindingDomain, RiskLevel
from app.services.analysis.checklist import normalize_title, reconcile_compliance_issues


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("No Verified FDA Status!") == "no verified fda status"


def test_normalize_title_collapses_whitespace_and_punctuation_variants():
    assert normalize_title("FDA   status -- unresolved") == normalize_title("FDA, status: unresolved.")


def _mock_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_reconcile_creates_new_open_issue_for_unmatched_finding():
    product_id = uuid.uuid4()
    run_id = uuid.uuid4()
    finding = MagicMock(
        domain=FindingDomain.FDA_REGULATORY, title="No verified FDA status",
        description="desc", risk=RiskLevel.CRITICAL,
    )

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add() is sync, unlike execute()/commit()
    db.execute.side_effect = [_mock_result([]), _mock_result([finding])]

    await reconcile_compliance_issues(db, product_id, run_id)

    assert db.add.call_count == 1
    added = db.add.call_args[0][0]
    assert added.title == "No verified FDA status"
    assert added.status == ComplianceIssueStatus.OPEN
    assert added.first_detected_run_id == run_id
    assert added.product_id == product_id
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_keeps_matching_open_issue_open_and_updates_it():
    product_id = uuid.uuid4()
    run_id = uuid.uuid4()
    existing_issue = MagicMock(
        domain=FindingDomain.FDA_REGULATORY, normalized_title="no verified fda status",
        status=ComplianceIssueStatus.OPEN,
    )
    finding = MagicMock(
        domain=FindingDomain.FDA_REGULATORY, title="No verified FDA status",
        description="updated description", risk=RiskLevel.HIGH,
    )

    db = AsyncMock()
    db.execute.side_effect = [_mock_result([existing_issue]), _mock_result([finding])]

    await reconcile_compliance_issues(db, product_id, run_id)

    assert db.add.call_count == 0  # matched, not recreated as a duplicate
    assert existing_issue.last_seen_run_id == run_id
    assert existing_issue.description == "updated description"
    assert existing_issue.risk == RiskLevel.HIGH
    assert existing_issue.status == ComplianceIssueStatus.OPEN  # untouched


@pytest.mark.asyncio
async def test_reconcile_resolves_issue_no_longer_found_in_new_run():
    product_id = uuid.uuid4()
    run_id = uuid.uuid4()
    existing_issue = MagicMock(
        domain=FindingDomain.FDA_REGULATORY, normalized_title="no verified fda status",
        status=ComplianceIssueStatus.OPEN,
    )

    db = AsyncMock()
    db.execute.side_effect = [_mock_result([existing_issue]), _mock_result([])]

    await reconcile_compliance_issues(db, product_id, run_id)

    assert existing_issue.status == ComplianceIssueStatus.RESOLVED
    assert existing_issue.resolved_run_id == run_id
    assert existing_issue.resolved_at is not None


@pytest.mark.asyncio
async def test_reconcile_matches_across_minor_wording_variance():
    # Same underlying issue, different punctuation/casing between runs --
    # normalized-title matching should treat it as the same issue rather
    # than creating a duplicate. (This is the documented limitation of the
    # matching heuristic: it only survives *minor* variance like this, not
    # a genuine rewording.)
    product_id = uuid.uuid4()
    run_id = uuid.uuid4()
    existing_issue = MagicMock(
        domain=FindingDomain.MARKETING, normalized_title="unsubstantiated diagnostic claim",
        status=ComplianceIssueStatus.OPEN,
    )
    finding = MagicMock(
        domain=FindingDomain.MARKETING, title="Unsubstantiated Diagnostic Claim!",
        description="d", risk=RiskLevel.HIGH,
    )

    db = AsyncMock()
    db.execute.side_effect = [_mock_result([existing_issue]), _mock_result([finding])]

    await reconcile_compliance_issues(db, product_id, run_id)

    assert db.add.call_count == 0
    assert existing_issue.status == ComplianceIssueStatus.OPEN


@pytest.mark.asyncio
async def test_reconcile_treats_same_title_in_different_domains_as_different_issues():
    product_id = uuid.uuid4()
    run_id = uuid.uuid4()
    existing_issue = MagicMock(
        domain=FindingDomain.FDA_REGULATORY, normalized_title="missing documentation",
        status=ComplianceIssueStatus.OPEN,
    )
    finding = MagicMock(
        domain=FindingDomain.BILLING, title="Missing documentation",
        description="d", risk=RiskLevel.MEDIUM,
    )

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add() is sync, unlike execute()/commit()
    db.execute.side_effect = [_mock_result([existing_issue]), _mock_result([finding])]

    await reconcile_compliance_issues(db, product_id, run_id)

    # Different domain -> treated as a distinct issue, not a match.
    assert db.add.call_count == 1
    # And the old one wasn't seen this run, so it resolves.
    assert existing_issue.status == ComplianceIssueStatus.RESOLVED
