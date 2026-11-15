import asyncio
import logging
import uuid
from typing import List, Optional
import pymupdf as fitz

from app.core.exceptions import ValidationException
from app.schemas.extraction import ExtractedDocument, ExtractedPage, ExtractedTable
from app.services.extractors.base import BaseDocumentExtractor
from app.services.extractors.normalizer import TextNormalizer

logger = logging.getLogger("enterprise_rag.extractors.pdf")


class PdfDocumentExtractor(BaseDocumentExtractor):
    """High-performance PDF extractor utilizing PyMuPDF (fitz) with layout and table awareness."""

    async def extract(
        self,
        file_content: bytes,
        file_name: str,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> ExtractedDocument:
        """Asynchronously extracts structured pages and tables from PDF bytes."""
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
        """Synchronous PyMuPDF extraction executed within thread pool worker."""
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
        except Exception as exc:
            logger.error(f"Failed to open PDF stream for '{file_name}': {exc}")
            raise ValidationException(f"Corrupted or invalid PDF document: {exc}")

        try:
            pages: List[ExtractedPage] = []
            all_tables: List[ExtractedTable] = []
            raw_page_texts: List[str] = []
            table_global_idx = 0

            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                page = doc[page_idx]

                # 1. Extract and format tables on page
                page_tables: List[ExtractedTable] = []
                try:
                    tabs = page.find_tables()
                    for tab in tabs:
                        table_global_idx += 1
                        extracted_rows = tab.extract()
                        if not extracted_rows:
                            continue

                        headers = [str(c or "").strip() for c in extracted_rows[0]]
                        data_rows = [
                            [str(c or "").strip() for c in r] for r in extracted_rows[1:]
                        ]
                        md_table = TextNormalizer.format_markdown_table(headers, data_rows)

                        t_obj = ExtractedTable(
                            table_index=table_global_idx,
                            page_number=page_num,
                            num_rows=len(extracted_rows),
                            num_cols=len(headers),
                            markdown=md_table,
                            headers=headers,
                            rows=data_rows,
                        )
                        page_tables.append(t_obj)
                        all_tables.append(t_obj)
                except Exception as t_exc:
                    logger.debug(f"Table detection skipped on page {page_num} of '{file_name}': {t_exc}")

                # 2. Extract plain text
                raw_text = page.get_text("text")
                raw_page_texts.append(raw_text)

                # Append formatted tables to page text for grounded retrieval
                combined_page_text = raw_text
                if page_tables:
                    combined_page_text += "\n\n### Extracted Tables:\n" + "\n\n".join(
                        t.markdown for t in page_tables
                    )

                pages.append(
                    ExtractedPage(
                        page_number=page_num,
                        text=combined_page_text,
                        raw_text=raw_text,
                        tables=page_tables,
                        metadata={
                            "width": page.rect.width,
                            "height": page.rect.height,
                            "rotation": page.rotation,
                        },
                    )
                )

            # 3. Deduplicate repeating headers and footers across pages
            cleaned_texts = TextNormalizer.deduplicate_headers_footers(
                [p.text for p in pages]
            )

            # 4. Normalize and clean final page texts
            for i, page_obj in enumerate(pages):
                page_obj.text = TextNormalizer.clean_text(cleaned_texts[i])
                page_obj.metadata["word_count"] = len(page_obj.text.split())
                page_obj.metadata["char_count"] = len(page_obj.text)

            # 5. Build full document text
            full_text = "\n\n".join(
                f"--- Page {p.page_number} ---\n{p.text}" for p in pages if p.text.strip()
            )

            # Extract native PDF metadata
            pdf_meta = doc.metadata or {}
            doc_meta = {
                "title": pdf_meta.get("title") or file_name,
                "author": pdf_meta.get("author"),
                "creation_date": pdf_meta.get("creationDate"),
                "mod_date": pdf_meta.get("modDate"),
                "total_pages": len(pages),
                "total_tables": len(all_tables),
            }

            parsed_doc_id = uuid.UUID(document_id) if document_id else None
            return ExtractedDocument(
                document_id=parsed_doc_id,
                file_type="PDF",
                file_name=file_name,
                full_text=full_text,
                pages=pages,
                tables=all_tables,
                metadata=doc_meta,
            )

        finally:
            doc.close()
