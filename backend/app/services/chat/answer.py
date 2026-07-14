"""Project-scoped Q&A chat (Milestone 7): one retrieval + one structured-
output LLM call per question, grounded only in this project's evidence plus
the shared Authority Library -- same cost profile as a single pipeline
stage, not the full 7-stage analysis. Never a substitute for the full
compliance analysis pipeline; the chat module prompt (prompts/chat_qa.md)
says so explicitly and requires every claim to carry a citation_label.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.models.enums import CollectionType
from app.models.product import Product
from app.models.project import Project
from app.schemas.chat_llm import ChatAnswerResult
from app.services.analysis.prompt_composer import compose_messages
from app.services.analysis.prompts_service import get_active_master_prompt, load_module_prompt
from app.services.llm.base import LLMProvider
from app.services.llm.redaction import apply_redaction
from app.services.retrieval.hybrid_search import RetrievalFilter, RetrievedChunk, hybrid_search
from app.services.storage.settings_store import load_runtime_settings

CHAT_MAX_TOKENS = 4000
HISTORY_TURNS = 3  # last N user/assistant pairs included as light conversational context


def _resolve_citation_dicts(labels: list[str], chunk_lookup: dict[str, RetrievedChunk]) -> list[dict]:
    citations = []
    for label in labels:
        chunk = chunk_lookup.get(label)
        if chunk is None:
            continue
        citations.append(
            {
                "role": "COMPANY_EVIDENCE" if chunk.collection_type == CollectionType.COMPANY else "CONTROLLING_AUTHORITY",
                "document_title": chunk.document_title,
                "section_title": chunk.heading_path,
                "page_number": chunk.page_number,
                "url": chunk.document_url,
                "quoted_text": chunk.text[:2000],
            }
        )
    return citations


async def ask_question(
    db: AsyncSession, project: Project, product: Product | None, llm: LLMProvider, model: str, question: str
) -> ChatMessage:
    settings = load_runtime_settings()

    user_message = ChatMessage(project_id=project.id, role="user", content=question)
    db.add(user_message)
    await db.flush()

    filters = RetrievalFilter(project_id=project.id)
    chunks = await hybrid_search(db, question, filters, top_k=15)
    chunks = [
        RetrievedChunk(
            **{
                **chunk.__dict__,
                "text": apply_redaction(
                    chunk.text,
                    redact_emails_enabled=settings.get("redact_emails", True),
                    redact_phones_enabled=settings.get("redact_phone_numbers", True),
                    redact_patient_ids_enabled=settings.get("redact_patient_identifiers", True),
                ),
            }
        )
        for chunk in chunks
    ]
    chunk_lookup = {c.citation_label: c for c in chunks}

    history_rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.project_id == project.id, ChatMessage.id != user_message.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_TURNS * 2)
        )
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

    master_prompt_version = await get_active_master_prompt(db)
    project_facts = {
        "project_name": project.name,
        "jurisdiction": project.jurisdiction,
        "product": product.name if product else None,
    }
    system_prompt, messages = compose_messages(
        master_prompt=master_prompt_version.content,
        module_prompt=load_module_prompt("chat_qa"),
        project_facts=project_facts,
        evidence_chunks=chunks,
        prior_stage_outputs={"recent_conversation": history} if history else None,
        enable_prompt_caching=settings.get("openrouter_prompt_caching", True),
    )
    # The user's actual question needs to be explicit in the user message,
    # not buried only inside the evidence bundle.
    messages[0]["content"] += f"\n\nUSER QUESTION:\n{question}"

    result = await llm.structured_completion(
        system_prompt=system_prompt,
        messages=messages,
        schema=ChatAnswerResult.model_json_schema(),
        schema_name="chat_qa",
        model=model,
        temperature=0,
        max_tokens=CHAT_MAX_TOKENS,
    )
    parsed = ChatAnswerResult.model_validate(result.content)

    assistant_message = ChatMessage(
        project_id=project.id,
        role="assistant",
        content=parsed.answer,
        citations_json=_resolve_citation_dicts(parsed.citation_labels, chunk_lookup),
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    return assistant_message
