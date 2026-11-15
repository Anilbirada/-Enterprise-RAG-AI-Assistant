from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.extraction import ExtractedDocument


class BaseDocumentExtractor(ABC):
    """Abstract base class for document format extractors."""

    @abstractmethod
    async def extract(
        self,
        file_content: bytes,
        file_name: str,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> ExtractedDocument:
        """Extracts text, structural hierarchy, and tables from raw file bytes.
        
        Args:
            file_content: Raw byte contents of the document.
            file_name: Original or sanitized filename.
            document_id: Optional database document UUID.
            
        Returns:
            ExtractedDocument containing pages, tables, and normalized text.
        """
        pass
