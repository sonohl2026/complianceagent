import fitz  # PyMuPDF

from app.services.parsing.base import Block, ParsedDocument, ParsingError


def parse_pdf(content: bytes) -> ParsedDocument:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises its own exception types
        raise ParsingError(f"Failed to open PDF: {exc}") from exc

    title = (doc.metadata or {}).get("title") or None
    blocks: list[Block] = []
    has_text_layer = False

    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            lines = block.get("lines")
            if not lines:
                continue
            text_parts = []
            max_font_size = 0.0
            for line in lines:
                for span in line.get("spans", []):
                    text_parts.append(span.get("text", ""))
                    max_font_size = max(max_font_size, span.get("size", 0.0))
            text = "".join(text_parts).strip()
            if not text:
                continue
            has_text_layer = True
            # Heuristic: larger-than-body font size on a short line looks like a heading.
            heading_level = 0
            if max_font_size >= 16 and len(text) < 120:
                heading_level = 1 if max_font_size >= 20 else 2
            blocks.append(Block(text=text, page_number=page_index + 1, heading_level=heading_level))

    doc.close()

    if not has_text_layer:
        raise ParsingError(
            "PDF has no extractable text layer (scanned document). "
            "Enable OCR in Settings to process this file, or upload a text-layer PDF."
        )

    return ParsedDocument(title=title, blocks=blocks)
