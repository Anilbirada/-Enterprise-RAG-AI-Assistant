from typing import Dict
from app.core.exceptions import ValidationException
from app.services.extractors.base import BaseDocumentExtractor
from app.services.extractors.docx_extractor import DocxDocumentExtractor
from app.services.extractors.normalizer import TextNormalizer
from app.services.extractors.pdf_extractor import PdfDocumentExtractor
from app.services.extractors.txt_extractor import TxtDocumentExtractor

_EXTRACTOR_REGISTRY: Dict[str, BaseDocumentExtractor] = {
    "PDF": PdfDocumentExtractor(),
    "DOCX": DocxDocumentExtractor(),
    "TXT": TxtDocumentExtractor(),
}


def get_document_extractor(file_type: str) -> BaseDocumentExtractor:
    """Returns the registered extractor instance for the given file type."""
    normalized_type = file_type.upper().strip().lstrip(".")
    extractor = _EXTRACTOR_REGISTRY.get(normalized_type)
    if not extractor:
        raise ValidationException(
            f"No document extractor registered for type '{file_type}'. "
            f"Available extractors: {', '.join(_EXTRACTOR_REGISTRY.keys())}"
        )
    return extractor


__all__ = [
    "BaseDocumentExtractor",
    "PdfDocumentExtractor",
    "DocxDocumentExtractor",
    "TxtDocumentExtractor",
    "TextNormalizer",
    "get_document_extractor",
]
