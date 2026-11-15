import pymupdf as fitz
import pytest
from app.core.exceptions import ValidationException
from app.services.extractors.pdf_extractor import PdfDocumentExtractor


def create_in_memory_pdf() -> bytes:
    """Generates a valid 2-page in-memory PDF using PyMuPDF."""
    doc = fitz.open()
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "Enterprise RAG Architecture Overview.\nThis section discusses retrieval mechanisms.")
    # Page 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "Vector Database and HNSW Indexing.\nDetails regarding pgvector performance.")
    
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_pdf_extractor_successful():
    """Test extracting text, pages, and metadata from a valid PDF."""
    pdf_bytes = create_in_memory_pdf()
    extractor = PdfDocumentExtractor()

    extracted = await extractor.extract(
        file_content=pdf_bytes,
        file_name="architecture.pdf",
    )

    assert extracted.file_type == "PDF"
    assert extracted.file_name == "architecture.pdf"
    assert extracted.total_pages == 2
    assert "Enterprise RAG Architecture Overview" in extracted.full_text
    assert "Vector Database and HNSW Indexing" in extracted.full_text

    # Page 1 checks
    assert extracted.pages[0].page_number == 1
    assert "retrieval mechanisms" in extracted.pages[0].text
    assert extracted.pages[0].metadata["width"] == 595

    # Page 2 checks
    assert extracted.pages[1].page_number == 2
    assert "pgvector performance" in extracted.pages[1].text


@pytest.mark.asyncio
async def test_pdf_extractor_corrupt_data():
    """Test extractor raises ValidationException when receiving corrupted PDF bytes."""
    extractor = PdfDocumentExtractor()
    corrupt_bytes = b"%PDF-1.7 Corrupt and unparseable garbage bytes"

    with pytest.raises(ValidationException) as exc:
        await extractor.extract(corrupt_bytes, "corrupt.pdf")
    assert "Corrupted or invalid PDF" in exc.value.message
