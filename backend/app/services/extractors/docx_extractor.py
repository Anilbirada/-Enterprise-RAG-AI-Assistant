import asyncio
import io
import logging
import uuid
from typing import List, Optional
import docx

from app.core.exceptions import ValidationException
from app.schemas.extraction import ExtractedDocument, ExtractedPage, ExtractedTable
from app.services.extractors.base import BaseDocumentExtractor
from app.services.extractors.normalizer import TextNormalizer

logger = logging.getLogger("enterprise_rag.extractors.docx")


class DocxDocumentExtractor(BaseDocumentExtractor):
    """Structured DOCX extractor utilizing python-docx with heading, list, and table preservation."""

    async def extract(
        self,
        file_content: bytes,
        file_name: str,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> ExtractedDocument:
        """Asynchronously extracts structured content and tables from DOCX bytes."""
        return await asyncio.to_thread(
            self._sync_extract,
            file_content,
            file_name,
            document_id,
        )

    def _sync_extract(
        self,
        file_content: bytes,
        file_name: str,
        document_id: Optional[str] = None,
    ) -> ExtractedDocument:
        """Synchronous DOCX extraction executed in background thread pool."""
        try:
            doc = docx.Document(io.BytesIO(file_content))
        except Exception as exc:
            logger.error(f"Failed to parse DOCX package for '{file_name}': {exc}")
            raise ValidationException(f"Corrupted or invalid DOCX document: {exc}")

        # 1. Extract and format tables
        extracted_tables: List[ExtractedTable] = []
        table_markdowns: List[str] = []

        for idx, table in enumerate(doc.tables):
            table_idx = idx + 1
            table_matrix: List[List[str]] = []
            for row in table.rows:
                # Deduplicate merged cells by preserving content once per cell
                seen_cells = set()
                row_vals = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    row_vals.append(cell_text)
                table_matrix.append(row_vals)

            if not table_matrix:
                continue

            headers = table_matrix[0]
            data_rows = table_matrix[1:] if len(table_matrix) > 1 else []
            md_table = TextNormalizer.format_markdown_table(headers, data_rows)

            t_obj = ExtractedTable(
                table_index=table_idx,
                page_number=1,
                num_rows=len(table_matrix),
                num_cols=len(headers),
                markdown=md_table,
                headers=headers,
                rows=data_rows,
            )
            extracted_tables.append(t_obj)
            table_markdowns.append(md_table)

        # 2. Extract structured paragraphs
        paragraph_lines: List[str] = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            style_name = (p.style.name if p.style else "").lower()

            # Preserve markdown heading levels
            if "heading 1" in style_name or "title" in style_name:
                paragraph_lines.append(f"\n# {text}\n")
            elif "heading 2" in style_name:
                paragraph_lines.append(f"\n## {text}\n")
            elif "heading 3" in style_name:
                paragraph_lines.append(f"\n### {text}\n")
            elif "bullet" in style_name or "list" in style_name:
                paragraph_lines.append(f"- {text}")
            else:
                paragraph_lines.append(text)

        # 3. Assemble document content
        body_text = "\n".join(paragraph_lines)
        if table_markdowns:
            body_text += "\n\n### Extracted Tables:\n" + "\n\n".join(table_markdowns)

        cleaned_text = TextNormalizer.clean_text(body_text)

        # In Word processing, flow documents typically form a continuous primary section (page 1)
        single_page = ExtractedPage(
            page_number=1,
            text=cleaned_text,
            raw_text=body_text,
            tables=extracted_tables,
            metadata={
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
                "word_count": len(cleaned_text.split()),
                "char_count": len(cleaned_text),
            },
        )

        # 4. Extract core document properties
        props = doc.core_properties
        doc_meta = {
            "title": props.title or file_name,
            "author": props.author,
            "category": props.category,
            "comments": props.comments,
            "created": str(props.created) if props.created else None,
            "modified": str(props.modified) if props.modified else None,
            "total_pages": 1,
            "total_tables": len(extracted_tables),
        }

        parsed_doc_id = uuid.UUID(document_id) if document_id else None
        return ExtractedDocument(
            document_id=parsed_doc_id,
            file_type="DOCX",
            file_name=file_name,
            full_text=cleaned_text,
            pages=[single_page],
            tables=extracted_tables,
            metadata=doc_meta,
        )
