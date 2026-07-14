"""Extract links and page metadata from crawled HTML. Text/heading extraction
for citation/chunking purposes reuses app.services.parsing.parsers.html_parser
(the same parser used for uploaded HTML documents) rather than duplicating it.
"""

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

PDF_EXTENSION = ".pdf"


@dataclass
class ExtractedPage:
    title: str | None
    canonical_url: str | None
    meta_description: str | None
    links: list[str] = field(default_factory=list)
    pdf_links: list[str] = field(default_factory=list)
    word_count: int = 0


def extract_page(html: str, page_url: str) -> ExtractedPage:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else None

    canonical_url = None
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = urljoin(page_url, canonical_tag["href"])

    meta_description = None
    description_tag = soup.find("meta", attrs={"name": "description"})
    if description_tag and description_tag.get("content"):
        meta_description = description_tag["content"].strip()

    links: list[str] = []
    pdf_links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(page_url, href)
        scheme = urlsplit(absolute).scheme
        if scheme not in ("http", "https"):
            continue
        if urlsplit(absolute).path.lower().endswith(PDF_EXTENSION):
            pdf_links.append(absolute)
        else:
            links.append(absolute)

    body_text = soup.get_text(" ", strip=True)
    word_count = len(body_text.split())

    return ExtractedPage(
        title=title,
        canonical_url=canonical_url,
        meta_description=meta_description,
        links=links,
        pdf_links=pdf_links,
        word_count=word_count,
    )
