"""Structure-aware chunking.

Preferred split order per build spec §11.1: heading hierarchy, then paragraph
boundaries, then table boundaries, then page boundaries, then a token-size
limit as the last resort. We approximate token count from word count (no
tokenizer dependency) since this only needs to be good enough to target the
~600-1000 token chunk size the spec calls for, not exact.
"""

from dataclasses import dataclass

from app.services.parsing.base import ParsedDocument

MIN_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 1000


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    heading_path: str | None
    start_offset: int
    end_offset: int
    citation_label: str
    token_count: int


def approx_token_count(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def _citation_label(document_title: str, page_number: int | None, heading_path: str | None) -> str:
    parts = [document_title]
    if page_number is not None:
        parts.append(f"p.{page_number}")
    if heading_path:
        parts.append(f"§{heading_path}")
    return " ".join(parts)


def chunk_document(parsed: ParsedDocument, document_title: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []

    current_texts: list[str] = []
    current_tokens = 0
    current_page: int | None = None
    offset = 0
    chunk_index = 0

    def heading_path_str() -> str | None:
        return " > ".join(t for _, t in heading_stack) if heading_stack else None

    def flush() -> None:
        nonlocal current_texts, current_tokens, current_page, offset, chunk_index
        if not current_texts:
            return
        text = "\n\n".join(current_texts)
        start = offset
        end = start + len(text)
        heading_path = heading_path_str()
        chunks.append(
            Chunk(
                text=text,
                chunk_index=chunk_index,
                page_number=current_page,
                section_title=heading_stack[-1][1] if heading_stack else None,
                heading_path=heading_path,
                start_offset=start,
                end_offset=end,
                citation_label=_citation_label(document_title, current_page, heading_path),
                token_count=approx_token_count(text),
            )
        )
        chunk_index += 1
        offset = end + 2
        current_texts = []
        current_tokens = 0
        current_page = None

    for block in parsed.blocks:
        if block.heading_level > 0:
            flush()
            while heading_stack and heading_stack[-1][0] >= block.heading_level:
                heading_stack.pop()
            heading_stack.append((block.heading_level, block.text))
            continue

        block_tokens = approx_token_count(block.text)
        if current_tokens + block_tokens > MAX_CHUNK_TOKENS and current_tokens >= MIN_CHUNK_TOKENS:
            flush()

        if current_page is None:
            current_page = block.page_number
        current_texts.append(block.text)
        current_tokens += block_tokens

    flush()
    return chunks
