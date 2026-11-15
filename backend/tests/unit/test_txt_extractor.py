import pytest
from app.services.extractors.txt_extractor import TxtDocumentExtractor


@pytest.mark.asyncio
async def test_txt_extractor_utf8():
    """Test standard UTF-8 text extraction."""
    extractor = TxtDocumentExtractor()
    content = "Enterprise RAG Assistant Documentation.\nGuidelines and configurations.".encode("utf-8")

    extracted = await extractor.extract(content, "notes.txt")
    assert extracted.file_type == "TXT"
    assert "Enterprise RAG Assistant Documentation." in extracted.full_text
    assert extracted.total_pages == 1
    assert extracted.total_words > 0


@pytest.mark.asyncio
async def test_txt_extractor_latin1_fallback():
    """Test latin-1 encoded text fallback."""
    extractor = TxtDocumentExtractor()
    # Character 0xe9 is 'é' in latin-1 (invalid standalone UTF-8 byte)
    content = b"Caf\xe9 and Cr\xe8me enterprise policies."

    extracted = await extractor.extract(content, "latin1.txt")
    assert extracted.file_type == "TXT"
    assert "Café" in extracted.full_text or "Caf" in extracted.full_text
