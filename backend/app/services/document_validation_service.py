import hashlib
import io
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import AsyncIterator, Tuple
from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import ValidationException

logger = logging.getLogger("enterprise_rag.document_validation")

# Common magic byte signatures
PDF_MAGIC_BYTES = b"%PDF-"
ZIP_MAGIC_BYTES = b"PK\x03\x04"


def sanitize_filename(original_filename: str) -> str:
    """Sanitizes user-provided filename to prevent path traversal and shell injection.
    
    1. Extracts pure filename (stripping directory components).
    2. Removes null bytes and control characters.
    3. Restricts characters to alphanumerics, underscores, hyphens, and single dots.
    4. Ensures file has a safe base name.
    """
    if not original_filename or not original_filename.strip():
        return "document.bin"

    # Strip directory components (handles both Unix and Windows separators)
    clean_name = os.path.basename(original_filename.replace("\\", "/")).strip()
    
    # Remove null bytes and non-printable characters
    clean_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", clean_name)

    # Disallow leading dot files (e.g. .htaccess, .env)
    if clean_name.startswith("."):
        clean_name = f"uploaded_{clean_name.lstrip('.')}"

    # Extract stem and extension
    name_path = Path(clean_name)
    stem = name_path.stem
    ext = name_path.suffix.lower()

    # Sanitize stem (alphanumerics, underscores, hyphens)
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_")

    if not safe_stem:
        safe_stem = "uploaded_document"

    # Limit stem length to 100 characters to prevent filesystem truncation issues
    safe_stem = safe_stem[:100]

    return f"{safe_stem}{ext}"


def validate_file_extension(filename: str) -> str:
    """Validates that file extension is supported and returns normalized extension."""
    settings = get_settings()
    ext = Path(filename).suffix.lower()

    if not ext:
        raise ValidationException(
            "Uploaded file lacks a valid extension. Supported formats: "
            + ", ".join(settings.ALLOWED_FILE_EXTENSIONS)
        )

    if ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise ValidationException(
            f"File extension '{ext}' is not permitted. Supported formats: "
            + ", ".join(settings.ALLOWED_FILE_EXTENSIONS)
        )

    return ext


def inspect_magic_signature(header_bytes: bytes, ext: str) -> Tuple[str, str]:
    """Inspects file signature (magic bytes) to ensure consistency with declared extension.
    
    Returns:
        (file_type, canonical_mime_type)
    """
    if not header_bytes:
        raise ValidationException("Uploaded file is empty (0 bytes).")

    if ext == ".pdf":
        if not header_bytes.startswith(PDF_MAGIC_BYTES):
            raise ValidationException(
                "Invalid PDF format: file header does not contain standard %PDF- magic signature."
            )
        return ("PDF", "application/pdf")

    elif ext == ".docx":
        if not header_bytes.startswith(ZIP_MAGIC_BYTES):
            raise ValidationException(
                "Invalid DOCX format: file header does not contain standard OpenXML/ZIP PK signature."
            )
        return (
            "DOCX",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    elif ext == ".txt":
        if b"\x00" in header_bytes:
            raise ValidationException("Invalid TXT format: binary null bytes detected.")
        try:
            header_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationException("Invalid TXT format: content is not valid UTF-8 text.")
        return ("TXT", "text/plain")

    raise ValidationException(f"Unsupported file type for extension '{ext}'.")


def verify_docx_package(file_bytes_or_path: Path | bytes) -> None:
    """Deep inspection of DOCX package structure to prevent disguised or corrupt ZIP archives."""
    try:
        if isinstance(file_bytes_or_path, Path):
            zf = zipfile.ZipFile(file_bytes_or_path, "r")
        else:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes_or_path), "r")

        with zf:
            namelist = zf.namelist()
            # Valid Word OpenXML packages MUST contain [Content_Types].xml or word/ directory
            has_content_types = "[Content_Types].xml" in namelist
            has_word_dir = any(name.startswith("word/") for name in namelist)

            if not (has_content_types or has_word_dir):
                raise ValidationException(
                    "Malformed DOCX: package missing standard OpenXML document structures ([Content_Types].xml or word/)."
                )
    except zipfile.BadZipFile:
        raise ValidationException("Corrupted DOCX: file is not a valid ZIP archive.")


async def create_bounded_upload_stream(
    upload_file: UploadFile,
    max_size_bytes: int,
    chunk_size: int = 65536,
) -> Tuple[AsyncIterator[bytes], bytes]:
    """Reads the initial verification header and provides a size-bounded chunked stream."""
    # Read the first 4KB to verify file signature
    header_chunk = await upload_file.read(4096)
    if not header_chunk:
        raise ValidationException("Uploaded file is empty (0 bytes).")

    async def _stream_generator() -> AsyncIterator[bytes]:
        yielded_bytes = len(header_chunk)
        if yielded_bytes > max_size_bytes:
            raise ValidationException(
                f"File size exceeds maximum permitted limit of {max_size_bytes / (1024 * 1024):.1f} MB."
            )
        yield header_chunk

        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            yielded_bytes += len(chunk)
            if yielded_bytes > max_size_bytes:
                raise ValidationException(
                    f"File size exceeds maximum permitted limit of {max_size_bytes / (1024 * 1024):.1f} MB."
                )
            yield chunk

    return _stream_generator(), header_chunk
