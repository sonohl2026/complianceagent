"""Project-scoped Q&A chat (Milestone 7). Synchronous, not job-queued --
one retrieval + one small structured-output LLM call per question is fast
enough to answer within a single HTTP request (unlike the full multi-stage
analysis pipeline). Not preflight-credit-checked like starting a full
analysis (app.services.llm.cost_estimate.preflight_credit_check estimates
cost against the *full 7-stage pipeline's* worst case, which would give a
misleading answer for one cheap chat call)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat_message import ChatMessage
from app.models.product import Product
from app.models.project import Project
from app.schemas.chat import ChatMessageRead, ChatQuestionRequest
from app.services.chat.answer import ask_question
from app.services.llm.base import LLMProviderError, LLMValidationError
from app.services.llm.openrouter_provider import OpenRouterProvider
from app.services.storage.settings_store import load_runtime_settings

router = APIRouter()


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageRead])
async def list_chat_messages(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.project_id == project_id).order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


@router.post("/projects/{project_id}/chat", response_model=ChatMessageRead, status_code=201)
async def ask_project_question(
    project_id: uuid.UUID, payload: ChatQuestionRequest, db: AsyncSession = Depends(get_db)
) -> ChatMessage:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    product = await db.get(Product, project.default_product_id) if project.default_product_id else None

    runtime_settings = load_runtime_settings()
    if not runtime_settings.get("openrouter_api_key"):
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter API key configured. Add one in Settings before using chat.",
        )
    model = runtime_settings.get("openrouter_model") or ""
    if not model:
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter model configured. Set an exact model slug in Settings before using chat.",
        )

    try:
        llm = OpenRouterProvider(api_key=runtime_settings.get("openrouter_api_key"))
        return await ask_question(db, project, product, llm, model, payload.question)
    except (LLMProviderError, LLMValidationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
