import os
import shutil
import tempfile
import pytest
from pathlib import Path
from app.services.storage.local import LocalStorageProvider


@pytest.fixture
def temp_storage_dir():
    """Provides an isolated temporary directory for storage provider testing."""
    temp_dir = tempfile.mkdtemp(prefix="rag_test_storage_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_local_storage_save_get_delete(temp_storage_dir: Path):
    """Test saving, retrieving, checking existence, and deleting a file."""
    provider = LocalStorageProvider(base_dir=temp_storage_dir)

    test_content = b"Enterprise RAG Storage Engine Test Bytes"
    storage_key = "tenants/test-org/documents/doc-1/sample.pdf"

    async def _stream():
        yield test_content

    # 1. Save
    meta = await provider.save(
        stream=_stream(),
        storage_key=storage_key,
        content_type="application/pdf",
    )
    assert meta.file_size_bytes == len(test_content)
    assert meta.content_type == "application/pdf"
    assert len(meta.checksum_sha256) == 64

    # 2. Exists
    assert await provider.exists(storage_key) is True

    # 3. Get / Read back
    chunks = []
    async for chunk in provider.get(storage_key):
        chunks.append(chunk)
    assert b"".join(chunks) == test_content

    # 4. Delete
    deleted = await provider.delete(storage_key)
    assert deleted is True
    assert await provider.exists(storage_key) is False

    # 5. Delete non-existent returns False
    assert await provider.delete("non_existent_key.txt") is False


@pytest.mark.asyncio
async def test_path_traversal_detection(temp_storage_dir: Path):
    """Test that path traversal attempts are detected and rejected."""
    provider = LocalStorageProvider(base_dir=temp_storage_dir)

    async def _stream():
        yield b"Malicious data"

    # Attempt path traversal
    with pytest.raises(ValueError) as exc_info:
        await provider.save(
            stream=_stream(),
            storage_key="../../etc/passwd",
            content_type="text/plain",
        )
    assert "Path traversal detected" in str(exc_info.value)
