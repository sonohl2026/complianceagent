from dataclasses import dataclass, field


@dataclass
class Block:
    """One unit of extracted text with just enough structure for citation
    and chunking: which page/slide it came from, and whether it's a heading
    (and at what level) or body text."""

    text: str
    page_number: int | None = None
    heading_level: int = 0  # 0 = body text; 1-6 = heading level (h1..h6)


@dataclass
class ParsedDocument:
    title: str | None
    blocks: list[Block] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())


class ParsingError(Exception):
    pass
