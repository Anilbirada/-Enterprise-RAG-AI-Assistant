import logging
import uuid
from typing import Optional

from app.schemas.extraction import ExtractedDocument, ExtractedPage
from app.services.extractors.base import BaseDocumentExtractor
from app.services.extractors.normalizer import TextNormalizer

logger = logging.getLogger("enterprise_rag.extractors.txt")


class TxtDocumentExtractor(BaseDocumentExtractor):
    """Plain text document extractor with robust character encoding fallback."""

    async def extract(
        self,
        file_content: bytes,
        file_name: str,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> ExtractedDocument:
        """Extracts and normalizes raw text bytes."""
        # Try UTF-8 first, fallback to latin-1
        try:
            raw_text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"UTF-8 decoding failed for '{file_name}', falling back to latin-1")
            raw_text = file_content.decode("latin-1", errors="replace")

        cleaned_text = TextNormalizer.clean_text(raw_text)

        page = ExtractedPage(
            page_number=1,
            text=cleaned_text,
            raw_text=raw_text,
            tables=[],
            metadata={
                "word_count": len(cleaned_text.split()),
                "char_count": len(cleaned_text),
            },
        )

        parsed_doc_id = uuid.UUID(document_id) if document_id else None
        return ExtractedDocument(
            document_id=parsed_doc_id,
            file_type="TXT",
            file_name=file_name,
            full_text=cleaned_text,
            pages=[page],
            tables=[],
            metadata={
                "title": file_name,
                "total_pages": 1,
                "total_tables": 0,
            },
        )
