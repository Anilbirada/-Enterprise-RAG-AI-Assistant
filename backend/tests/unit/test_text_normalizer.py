import pytest
from app.services.extractors.normalizer import TextNormalizer


def test_normalize_unicode():
    """Test standardizing unicode ligatures and special characters with NFKC."""
    # Ligature 'fi' and curly quotes
    raw_text = "The \ufb01rst \u201cquote\u201d with non-breaking\xa0space and zero\u200bwidth."
    normalized = TextNormalizer.normalize_unicode(raw_text)
    assert "first" in normalized
    assert '"quote"' in normalized
    assert "\xa0" not in normalized
    assert "\u200b" not in normalized


def test_strip_control_characters():
    """Test stripping non-printable control chars while preserving \n, \t."""
    raw_text = "Line 1\x00\x07\x08\nLine 2\twith tab\x1f\x7f."
    cleaned = TextNormalizer.strip_control_characters(raw_text)
    assert cleaned == "Line 1\nLine 2\twith tab."


def test_clean_text_whitespace():
    """Test collapsing multiple spaces, tabs, and excess newlines."""
    raw_text = "   Paragraph one   with    spaces.   \r\n\r\n\r\n\r\n   Paragraph two.   \n"
    cleaned = TextNormalizer.clean_text(raw_text)
    assert cleaned == "Paragraph one with spaces.\n\nParagraph two."


def test_format_markdown_table():
    """Test converting 2D matrix into standard Markdown table."""
    headers = ["Name", "Department", "Role"]
    rows = [
        ["Alice", "Engineering", "Architect"],
        ["Bob", "Product", "Manager"],
        ["Charlie", "Security", "Lead"],
    ]
    md = TextNormalizer.format_markdown_table(headers, rows)
    assert "| Name | Department | Role |" in md
    assert "| --- | --- | --- |" in md
    assert "| Alice | Engineering | Architect |" in md
    assert "| Bob | Product | Manager |" in md


def test_deduplicate_headers_footers():
    """Test detecting and removing repetitive running headers/footers across pages."""
    pages = [
        "ACME ENTERPRISE CONFIDENTIAL\nIntroduction to RAG.\nPage 1 of 4",
        "ACME ENTERPRISE CONFIDENTIAL\nArchitecture details and diagrams.\nPage 2 of 4",
        "ACME ENTERPRISE CONFIDENTIAL\nDatabase schema and pgvector.\nPage 3 of 4",
        "ACME ENTERPRISE CONFIDENTIAL\nConclusion and references.\nPage 4 of 4",
    ]
    deduped = TextNormalizer.deduplicate_headers_footers(pages)
    for p in deduped:
        assert "ACME ENTERPRISE CONFIDENTIAL" not in p
        assert "Page 1 of 4" not in p
    assert "Introduction to RAG." in deduped[0]
    assert "Architecture details and diagrams." in deduped[1]
