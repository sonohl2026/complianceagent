"""Scheduled recrawls and material-change alerts (Milestone 8)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.monitoring import Alert, ScheduledRecrawl
from app.models.project import Project
from app.schemas.monitoring import (
    AlertRead,
    AlertWithProject,
    ScheduledRecrawlCreate,
    ScheduledRecrawlRead,
    ScheduledRecrawlUpdate,
)
from app.services.crawling.crawler import CrawlSettings

router = APIRouter()


@router.post("/projects/{project_id}/scheduled-recrawls", response_model=ScheduledRecrawlRead, status_code=201)
async def create_scheduled_recrawl(
    project_id: uuid.UUID, payload: ScheduledRecrawlCreate, db: AsyncSession = Depends(get_db)
) -> ScheduledRecrawl:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    app_settings = get_settings()
    crawl_settings = CrawlSettings(
        start_url=payload.start_url,
        max_pages=payload.max_pages or app_settings.max_crawl_pages,
        max_depth=payload.max_depth if payload.max_depth is not None else app_settings.max_crawl_depth,
        follow_subdomains=payload.follow_subdomains,
        include_pdfs=payload.include_pdfs,
        crawl_delay_ms=app_settings.crawl_delay_ms,
    )

    schedule = ScheduledRecrawl(
        project_id=project_id,
        start_url=payload.start_url,
        crawl_settings_json=crawl_settings.as_dict(),
        interval_hours=payload.interval_hours,
        # Fires on the next Beat tick (within 30 min) rather than waiting a
        # full interval, so setting one up gives quick feedback that it works.
        next_run_at=datetime.now(timezone.utc),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/projects/{project_id}/scheduled-recrawls", response_model=list[ScheduledRecrawlRead])
async def list_scheduled_recrawls(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ScheduledRecrawl]:
    result = await db.execute(
        select(ScheduledRecrawl)
        .where(ScheduledRecrawl.project_id == project_id)
        .order_by(ScheduledRecrawl.created_at.desc())
    )
    return list(result.scalars().all())


@router.put("/scheduled-recrawls/{schedule_id}", response_model=ScheduledRecrawlRead)
async def update_scheduled_recrawl(
    schedule_id: uuid.UUID, payload: ScheduledRecrawlUpdate, db: AsyncSession = Depends(get_db)
) -> ScheduledRecrawl:
    schedule = await db.get(ScheduledRecrawl, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled recrawl not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/scheduled-recrawls/{schedule_id}", status_code=204)
async def delete_scheduled_recrawl(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    schedule = await db.get(ScheduledRecrawl, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled recrawl not found")
    await db.delete(schedule)
    await db.commit()


@router.get("/alerts", response_model=list[AlertWithProject])
async def list_alerts(
    project_id: uuid.UUID | None = None,
    acknowledged: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AlertWithProject]:
    query = select(Alert, Project.name).join(Project, Alert.project_id == Project.id)
    if project_id is not None:
        query = query.where(Alert.project_id == project_id)
    if acknowledged is not None:
        query = query.where(Alert.acknowledged == acknowledged)
    query = query.order_by(Alert.created_at.desc())

    rows = (await db.execute(query)).all()
    return [
        AlertWithProject(**AlertRead.model_validate(alert).model_dump(), project_name=project_name)
        for alert, project_name in rows
    ]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(alert_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Alert:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await db.commit()
    await db.refresh(alert)
    return alert
