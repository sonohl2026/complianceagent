#!/usr/bin/env python3
"""Re-embed every chunk in a project (or the shared authority library).

Use this after changing LOCAL_EMBEDDING_MODEL, so stored embeddings stay
consistent with the configured model/version (build spec §5: "support
complete re-indexing when the model changes"). Also re-populates the
full-text search_vector column for each chunk.

Usage:
    python scripts/reindex_project.py <project-uuid>
    python scripts/reindex_project.py --authority
"""
import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.enums import CollectionType, ParseStatus
from app.models.source_document import SourceDocument
from app.services.embeddings.indexing import embed_document


async def reindex(*, project_id: uuid.UUID | None, authority_only: bool) -> None:
    async with AsyncSessionLocal() as db:
        query = select(SourceDocument).where(SourceDocument.parse_status == ParseStatus.COMPLETE)
        if authority_only:
            query = query.where(SourceDocument.collection_type == CollectionType.AUTHORITY)
        else:
            query = query.where(SourceDocument.project_id == project_id)

        documents = list((await db.execute(query)).scalars().all())
        if not documents:
            print("[reindex_project] No completed documents found in scope.")
            return

        total_chunks = 0
        for document in documents:
            count = await embed_document(db, document)
            total_chunks += count
            print(f"[reindex_project] Re-embedded {count} chunks for document {document.id} ({document.title!r})")

        print(f"[reindex_project] Done: {len(documents)} documents, {total_chunks} chunks re-embedded.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_id", nargs="?", help="UUID of the project to reindex")
    parser.add_argument(
        "--authority", action="store_true", help="Reindex the shared authority library instead of a project"
    )
    args = parser.parse_args()

    if not args.authority and not args.project_id:
        parser.error("Provide a project_id, or pass --authority to reindex the authority library.")

    project_uuid = uuid.UUID(args.project_id) if args.project_id else None
    asyncio.run(reindex(project_id=project_uuid, authority_only=args.authority))
    return 0


if __name__ == "__main__":
    sys.exit(main())
