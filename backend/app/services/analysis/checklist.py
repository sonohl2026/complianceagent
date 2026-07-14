"""Reconciles a just-completed analysis run's findings against the
product's durable compliance checklist (user-requested: show what's still
open vs. what got fixed after a small incremental site/document change,
without re-reading a whole new report every time).

Matching is a normalized-title + domain equality check -- deterministic and
free (no extra LLM call, consistent with the whole point of this feature
being a *cost* reduction). This is a real approximation: if the model
rewords a finding's title between runs, this reads it as a new issue rather
than the same one continuing to be open. Good enough for a first version;
a follow-up could match on embedding similarity instead of exact
normalized-title equality.
"""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Finding
from app.models.compliance_issue import ComplianceIssue
from app.models.enums import ComplianceIssueStatus


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


async def reconcile_compliance_issues(db: AsyncSession, product_id: uuid.UUID, analysis_run_id: uuid.UUID) -> None:
    open_issues = (
        await db.execute(
            select(ComplianceIssue).where(
                ComplianceIssue.product_id == product_id,
                ComplianceIssue.status == ComplianceIssueStatus.OPEN,
            )
        )
    ).scalars().all()
    open_by_key = {(issue.domain, issue.normalized_title): issue for issue in open_issues}

    findings = (
        await db.execute(select(Finding).where(Finding.analysis_run_id == analysis_run_id))
    ).scalars().all()

    matched_keys: set[tuple] = set()
    for finding in findings:
        key = (finding.domain, normalize_title(finding.title))
        matched_keys.add(key)
        existing = open_by_key.get(key)
        if existing:
            existing.last_seen_run_id = analysis_run_id
            existing.description = finding.description
            existing.risk = finding.risk
        else:
            db.add(
                ComplianceIssue(
                    product_id=product_id,
                    domain=finding.domain,
                    title=finding.title,
                    normalized_title=normalize_title(finding.title),
                    description=finding.description,
                    risk=finding.risk,
                    status=ComplianceIssueStatus.OPEN,
                    first_detected_run_id=analysis_run_id,
                    last_seen_run_id=analysis_run_id,
                )
            )

    for key, issue in open_by_key.items():
        if key not in matched_keys:
            issue.status = ComplianceIssueStatus.RESOLVED
            issue.resolved_run_id = analysis_run_id
            issue.resolved_at = datetime.now(timezone.utc)

    await db.commit()
