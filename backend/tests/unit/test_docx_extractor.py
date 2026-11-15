import io
import docx
import pytest
from app.core.exceptions import ValidationException
from app.services.extractors.docx_extractor import DocxDocumentExtractor


def create_in_memory_docx() -> bytes:
    """Generates a structured DOCX with headings, lists, and a table."""
    doc = docx.Document()
    doc.add_heading("Enterprise Security Policy", level=1)
    doc.add_paragraph("This document outlines tenant access controls.")
    doc.add_heading("Key Roles", level=2)
    doc.add_paragraph("Knowledge Manager", style="List Bullet")
    doc.add_paragraph("Org Administrator", style="List Bullet")

    # Add Table
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Role Name"
    table.cell(0, 1).text = "Access Level"
    table.cell(1, 0).text = "ORG_ADMIN"
    table.cell(1, 1).text = "Tenant Full"
    table.cell(2, 0).text = "EMPLOYEE"
    table.cell(2, 1).text = "Read Only"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_extractor_successful():
    """Test extracting headings, bullet points, tables, and metadata from DOCX."""
    docx_bytes = create_in_memory_docx()
    extractor = DocxDocumentExtractor()

    extracted = await extractor.extract(
        file_content=docx_bytes,
        file_name="security_policy.docx",
    )

    assert extracted.file_type == "DOCX"
    assert extracted.file_name == "security_policy.docx"
    assert extracted.total_pages == 1
    assert extracted.total_tables == 1

    # Verify heading conversion
    assert "# Enterprise Security Policy" in extracted.full_text
    assert "## Key Roles" in extracted.full_text

    # Verify bullet conversion
    assert "- Knowledge Manager" in extracted.full_text

    # Verify table conversion to Markdown
    assert "| Role Name | Access Level |" in extracted.full_text
    assert "| ORG_ADMIN | Tenant Full |" in extracted.full_text
    assert "| EMPLOYEE | Read Only |" in extracted.full_text

    # Verify table object
    table_obj = extracted.tables[0]
    assert table_obj.num_rows == 3
    assert table_obj.num_cols == 2
    assert table_obj.headers == ["Role Name", "Access Level"]


@pytest.mark.asyncio
async def test_docx_extractor_corrupt_data():
    """Test extractor raises ValidationException on invalid DOCX package."""
    extractor = DocxDocumentExtractor()
    corrupt_bytes = b"PK\x03\x04corrupted zip payload"

    with pytest.raises(ValidationException) as exc:
        await extractor.extract(corrupt_bytes, "corrupt.docx")
    assert "Corrupted or invalid DOCX" in exc.value.message
