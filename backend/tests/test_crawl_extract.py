from app.services.crawling.extract import extract_page

SAMPLE_HTML = """
<html>
<head>
  <title>SonoHL — Investigational Platform</title>
  <link rel="canonical" href="https://sonohl.com/product">
  <meta name="description" content="SonoHL acoustic-sensing platform overview.">
</head>
<body>
  <h1>Overview</h1>
  <p>SonoHL is investigational and not cleared by the FDA.</p>
  <a href="/about">About</a>
  <a href="https://sonohl.com/whitepaper.pdf">Whitepaper</a>
  <a href="https://competitor.com/">Competitor</a>
  <a href="mailto:info@sonohl.com">Email us</a>
  <a href="#top">Back to top</a>
  <a href="javascript:void(0)">No-op</a>
</body>
</html>
"""


def test_extracts_title_canonical_and_description():
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product?utm=1")
    assert result.title == "SonoHL — Investigational Platform"
    assert result.canonical_url == "https://sonohl.com/product"
    assert result.meta_description == "SonoHL acoustic-sensing platform overview."


def test_resolves_relative_links_to_absolute():
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product")
    assert "https://sonohl.com/about" in result.links


def test_separates_pdf_links_from_page_links():
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product")
    assert "https://sonohl.com/whitepaper.pdf" in result.pdf_links
    assert "https://sonohl.com/whitepaper.pdf" not in result.links


def test_excludes_mailto_anchor_and_fragment_only_links():
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product")
    assert not any(link.startswith("mailto:") for link in result.links)
    assert not any(link.startswith("javascript:") for link in result.links)
    assert "https://sonohl.com/product#top" not in result.links


def test_includes_offsite_links_unfiltered_scope_decision_left_to_caller():
    # extract_page() is scope-agnostic; the crawler orchestrator applies
    # same-domain filtering via url_utils.is_in_crawl_scope.
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product")
    assert "https://competitor.com/" in result.links


def test_word_count_is_positive():
    result = extract_page(SAMPLE_HTML, "https://sonohl.com/product")
    assert result.word_count > 0
