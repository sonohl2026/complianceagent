from bs4 import BeautifulSoup

from app.services.parsing.base import Block, ParsedDocument, ParsingError
from app.services.parsing.text_decode import decode_text

_HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}
_SKIP_TAGS = {"script", "style", "noscript", "template"}


def parse_html(content: bytes) -> ParsedDocument:
    html = decode_text(content)
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None

    blocks: list[Block] = []
    body = soup.body or soup
    for element in body.find_all(list(_HEADING_TAGS) + ["p", "li", "td", "blockquote"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        heading_level = _HEADING_TAGS.get(element.name, 0)
        blocks.append(Block(text=text, page_number=None, heading_level=heading_level))

    if not blocks:
        raise ParsingError("HTML contains no extractable text")

    return ParsedDocument(title=title, blocks=blocks)
