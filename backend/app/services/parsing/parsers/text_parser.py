from app.services.parsing.base import Block, ParsedDocument, ParsingError
from app.services.parsing.text_decode import decode_text


def parse_plain_text(content: bytes) -> ParsedDocument:
    text = decode_text(content)
    if not text.strip():
        raise ParsingError("Text file is empty")

    blocks: list[Block] = []
    for paragraph in text.split("\n\n"):
        stripped = paragraph.strip()
        if stripped:
            blocks.append(Block(text=stripped, page_number=None, heading_level=0))

    return ParsedDocument(title=None, blocks=blocks)


def parse_markdown(content: bytes) -> ParsedDocument:
    text = decode_text(content)
    if not text.strip():
        raise ParsingError("Markdown file is empty")

    blocks: list[Block] = []
    title = None
    buffer: list[str] = []

    def flush():
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(Block(text=joined, page_number=None, heading_level=0))
            buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            if heading_text:
                if title is None:
                    title = heading_text
                blocks.append(Block(text=heading_text, page_number=None, heading_level=min(level, 6)))
        elif stripped:
            buffer.append(stripped)
        else:
            flush()
    flush()

    return ParsedDocument(title=title, blocks=blocks)
