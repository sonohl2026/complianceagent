from app.services.parsing.base import Block, ParsedDocument
from app.services.parsing.chunking import MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS, chunk_document


def test_heading_always_starts_a_new_chunk_boundary():
    parsed = ParsedDocument(
        title="Doc",
        blocks=[
            Block(text="Intro", heading_level=1),
            Block(text="short body", heading_level=0, page_number=1),
            Block(text="Section Two", heading_level=1),
            Block(text="more body", heading_level=0, page_number=2),
        ],
    )
    chunks = chunk_document(parsed, "Doc")
    assert len(chunks) == 2
    assert chunks[0].section_title == "Intro"
    assert chunks[0].text == "short body"
    assert chunks[1].section_title == "Section Two"
    assert chunks[1].text == "more body"


def test_heading_path_nests_through_levels():
    parsed = ParsedDocument(
        title="Doc",
        blocks=[
            Block(text="Chapter 1", heading_level=1),
            Block(text="Section 1.1", heading_level=2),
            Block(text="body text here", heading_level=0),
        ],
    )
    chunks = chunk_document(parsed, "Doc")
    assert len(chunks) == 1
    assert chunks[0].heading_path == "Chapter 1 > Section 1.1"
    assert "§Chapter 1 > Section 1.1" in chunks[0].citation_label


def test_sibling_heading_pops_previous_subsection():
    parsed = ParsedDocument(
        title="Doc",
        blocks=[
            Block(text="Chapter 1", heading_level=1),
            Block(text="Section 1.1", heading_level=2),
            Block(text="body A", heading_level=0),
            Block(text="Section 1.2", heading_level=2),
            Block(text="body B", heading_level=0),
        ],
    )
    chunks = chunk_document(parsed, "Doc")
    assert chunks[-1].heading_path == "Chapter 1 > Section 1.2"


def test_long_body_splits_once_min_tokens_reached():
    # Build enough body text under one heading to force a token-limit split.
    long_paragraph = " ".join(["word"] * 200)  # ~260 approx tokens per block
    blocks = [Block(text="Only Section", heading_level=1)]
    blocks += [Block(text=long_paragraph, heading_level=0) for _ in range(6)]
    parsed = ParsedDocument(title="Doc", blocks=blocks)

    chunks = chunk_document(parsed, "Doc")

    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        assert chunk.token_count >= MIN_CHUNK_TOKENS
    for chunk in chunks:
        assert chunk.token_count <= MAX_CHUNK_TOKENS * 1.3  # one block may push slightly over


def test_citation_label_includes_page_when_present():
    parsed = ParsedDocument(title="Doc", blocks=[Block(text="body", page_number=3, heading_level=0)])
    chunks = chunk_document(parsed, "SonoHL Whitepaper")
    assert chunks[0].citation_label == "SonoHL Whitepaper p.3"


def test_offsets_are_contiguous_and_non_overlapping():
    parsed = ParsedDocument(
        title="Doc",
        blocks=[
            Block(text="Heading", heading_level=1),
            Block(text="first", heading_level=0),
            Block(text="Heading 2", heading_level=1),
            Block(text="second", heading_level=0),
        ],
    )
    chunks = chunk_document(parsed, "Doc")
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len("first")
    assert chunks[1].start_offset > chunks[0].end_offset
