import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractedTable(BaseModel):
    """Structured representation of an extracted table from a document."""
    table_index: int
    page_number: Optional[int] = None
    num_rows: int
    num_cols: int
    markdown: str = Field(description="Table formatted as GitHub Flavored Markdown")
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)


class ExtractedPage(BaseModel):
    """Extracted text, tables, and metadata for a single document page or section."""
    page_number: int
    text: str = Field(description="Normalized and structured page text")
    raw_text: str = Field(description="Unprocessed raw text as read from source")
    tables: List[ExtractedTable] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExtractedDocument(BaseModel):
    """Complete extracted document ready for chunking, embedding, and indexing."""
    document_id: Optional[uuid.UUID] = None
    file_type: str
    file_name: str
    full_text: str = Field(description="Concatenated, normalized full document text")
    pages: List[ExtractedPage] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_words(self) -> int:
        return len(self.full_text.split())

    @property
    def total_characters(self) -> int:
        return len(self.full_text)

    @property
    def total_tables(self) -> int:
        return len(self.tables)
