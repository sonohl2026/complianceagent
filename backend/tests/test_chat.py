import uuid

from app.models.enums import AuthorityLevel, CollectionType
from app.services.chat.answer import _resolve_citation_dicts
from app.services.retrieval.hybrid_search import RetrievedChunk


def _chunk(
    citation_label: str,
    collection_type: CollectionType = CollectionType.COMPANY,
    document_url: str | None = None,
    authority_level: AuthorityLevel | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Doc Title",
        collection_type=collection_type,
        authority_level=authority_level,
        text="Some evidence text here.",
        citation_label=citation_label,
        page_number=3,
        heading_path="Section 2",
        score=0.5,
        document_url=document_url,
    )


def test_resolve_citation_dicts_maps_company_evidence_role():
    chunk = _chunk("Doc p.1", collection_type=CollectionType.COMPANY)
    result = _resolve_citation_dicts(["Doc p.1"], {"Doc p.1": chunk})
    assert len(result) == 1
    assert result[0]["role"] == "COMPANY_EVIDENCE"
    assert result[0]["document_title"] == "Doc Title"
    assert result[0]["section_title"] == "Section 2"
    assert result[0]["page_number"] == 3


def test_resolve_citation_dicts_maps_authority_evidence_role():
    chunk = _chunk("Reg p.2", collection_type=CollectionType.AUTHORITY)
    result = _resolve_citation_dicts(["Reg p.2"], {"Reg p.2": chunk})
    assert result[0]["role"] == "CONTROLLING_AUTHORITY"


def test_resolve_citation_dicts_includes_url_when_present():
    chunk = _chunk("Doc p.1", document_url="https://example.com/page")
    result = _resolve_citation_dicts(["Doc p.1"], {"Doc p.1": chunk})
    assert result[0]["url"] == "https://example.com/page"


def test_resolve_citation_dicts_skips_unknown_labels_gracefully():
    # The model referenced a label that wasn't actually in the retrieved
    # evidence -- must not crash or fabricate a citation for it.
    result = _resolve_citation_dicts(["Nonexistent p.9"], {})
    assert result == []


def test_resolve_citation_dicts_truncates_long_quoted_text():
    chunk = _chunk("Doc p.1")
    chunk.text = "x" * 5000
    result = _resolve_citation_dicts(["Doc p.1"], {"Doc p.1": chunk})
    assert len(result[0]["quoted_text"]) == 2000
