import io
import zipfile
import pytest
from app.core.exceptions import ValidationException
from app.services.document_validation_service import (
    inspect_magic_signature,
    sanitize_filename,
    validate_file_extension,
    verify_docx_package,
)


def test_sanitize_filename():
    """Test sanitization of hazardous, weird, and path-traversing filenames."""
    assert sanitize_filename("safe_report.pdf") == "safe_report.pdf"
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe.pdf") == "cmd_exe.pdf"
    assert sanitize_filename(".hidden_file.docx") == "uploaded_hidden_file.docx"
    assert sanitize_filename("My quarterly report (Q3) [FINAL]!.pdf") == "My_quarterly_report_Q3_FINAL.pdf"
    assert sanitize_filename("") == "document.bin"
    assert sanitize_filename("   ") == "document.bin"


def test_validate_file_extension():
    """Test extension validation with allowlist."""
    assert validate_file_extension("report.pdf") == ".pdf"
    assert validate_file_extension("HANDBOOK.DOCX") == ".docx"
    assert validate_file_extension("notes.txt") == ".txt"

    with pytest.raises(ValidationException):
        validate_file_extension("malware.exe")

    with pytest.raises(ValidationException):
        validate_file_extension("script.sh")

    with pytest.raises(ValidationException):
        validate_file_extension("no_extension_file")


def test_inspect_magic_signature_pdf():
    """Test PDF magic bytes validation."""
    valid_pdf_header = b"%PDF-1.7 standard header bytes"
    file_type, mime = inspect_magic_signature(valid_pdf_header, ".pdf")
    assert file_type == "PDF"
    assert mime == "application/pdf"

    # Spoofed PDF header
    invalid_pdf_header = b"NOT_A_PDF fake data"
    with pytest.raises(ValidationException) as exc:
        inspect_magic_signature(invalid_pdf_header, ".pdf")
    assert "Invalid PDF format" in exc.value.message


def test_inspect_magic_signature_docx():
    """Test DOCX magic bytes validation."""
    valid_docx_header = b"PK\x03\x04zip header"
    file_type, mime = inspect_magic_signature(valid_docx_header, ".docx")
    assert file_type == "DOCX"
    assert "wordprocessingml" in mime

    # Spoofed DOCX header
    invalid_docx_header = b"MZ executable header"
    with pytest.raises(ValidationException) as exc:
        inspect_magic_signature(invalid_docx_header, ".docx")
    assert "Invalid DOCX format" in exc.value.message


def test_inspect_magic_signature_txt():
    """Test TXT magic bytes validation."""
    valid_txt = "Hello enterprise RAG assistant!".encode("utf-8")
    file_type, mime = inspect_magic_signature(valid_txt, ".txt")
    assert file_type == "TXT"
    assert mime == "text/plain"

    # Binary with null bytes
    binary_data = b"Hello\x00World\x00NullBytes"
    with pytest.raises(ValidationException) as exc:
        inspect_magic_signature(binary_data, ".txt")
    assert "null bytes detected" in exc.value.message


def test_verify_docx_package_valid():
    """Test that a genuine OpenXML DOCX archive passes package verification."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document></w:document>")

    verify_docx_package(buf.getvalue())


def test_verify_docx_package_missing_structures():
    """Test that an arbitrary zip (renamed as docx) is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("arbitrary_file.txt", "Some text")

    with pytest.raises(ValidationException) as exc:
        verify_docx_package(buf.getvalue())
    assert "missing standard OpenXML document structures" in exc.value.message
