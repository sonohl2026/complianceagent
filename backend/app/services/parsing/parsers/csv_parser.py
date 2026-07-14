import csv
import io

from app.services.parsing.base import Block, ParsedDocument, ParsingError
from app.services.parsing.text_decode import decode_text


def parse_csv(content: bytes) -> ParsedDocument:
    text = decode_text(content)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ParsingError("CSV contains no rows")

    blocks: list[Block] = []
    header = rows[0]
    blocks.append(Block(text=" | ".join(header), page_number=1, heading_level=1))
    for row in rows[1:]:
        if any(cell.strip() for cell in row):
            blocks.append(Block(text=" | ".join(row), page_number=1, heading_level=0))

    return ParsedDocument(title=None, blocks=blocks)
