from app.services.parsing.base import ParsedDocument, ParsingError
from app.services.parsing.parsers.csv_parser import parse_csv
from app.services.parsing.parsers.docx import parse_docx
from app.services.parsing.parsers.html_parser import parse_html
from app.services.parsing.parsers.pdf import parse_pdf
from app.services.parsing.parsers.pptx import parse_pptx
from app.services.parsing.parsers.text_parser import parse_markdown, parse_plain_text
from app.services.parsing.parsers.xlsx import parse_xlsx

_PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".xlsx": parse_xlsx,
    ".csv": parse_csv,
    ".html": parse_html,
    ".htm": parse_html,
    ".md": parse_markdown,
    ".txt": parse_plain_text,
}


def parse_document(extension: str, content: bytes) -> ParsedDocument:
    parser = _PARSERS.get(extension)
    if parser is None:
        raise ParsingError(f"No parser registered for extension {extension!r}")
    return parser(content)
