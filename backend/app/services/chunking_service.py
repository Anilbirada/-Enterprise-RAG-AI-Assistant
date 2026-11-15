import logging
import re
import uuid
from typing import List, Optional, Tuple
import tiktoken

from app.core.config import get_settings
from app.schemas.chunk import ChunkMetadata, ChunkingStatistics, DocumentChunkData
from app.schemas.extraction import ExtractedDocument, ExtractedPage

logger = logging.getLogger("enterprise_rag.chunking_service")


class ChunkingService:
    """Intelligent token-aware recursive document chunker with table and page structure preservation."""

    def __init__(
        self,
        chunk_size_tokens: Optional[int] = None,
        chunk_overlap_tokens: Optional[int] = None,
        encoding_name: str = "cl100k_base",
    ) -> None:
        settings = get_settings()
        self.chunk_size_tokens = chunk_size_tokens or settings.CHUNK_SIZE_TOKENS
        self.chunk_overlap_tokens = chunk_overlap_tokens or settings.CHUNK_OVERLAP_TOKENS
        
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError(
                f"Overlap tokens ({self.chunk_overlap_tokens}) must be strictly less than chunk size ({self.chunk_size_tokens})."
            )

        try:
            self.tokenizer = tiktoken.get_encoding(encoding_name)
        except Exception as exc:
            logger.warning(f"Failed loading tiktoken encoding '{encoding_name}', falling back to cl100k_base: {exc}")
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # Priority of semantic splitting boundaries
        self.separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

    def count_tokens(self, text: str) -> int:
        """Returns the exact number of tokens for a given text string."""
        if not text:
            return 0
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def _split_text_recursively(
        self,
        text: str,
        separators: List[str],
    ) -> List[str]:
        """Splits text recursively using the highest priority delimiter available."""
        if not text or not text.strip():
            return []

        # If already fits within chunk size, return immediately
        if self.count_tokens(text) <= self.chunk_size_tokens:
            return [text.strip()]

        if not separators:
            # Fallback: slice directly by token boundaries
            tokens = self.tokenizer.encode(text, disallowed_special=())
            chunks = []
            start = 0
            while start < len(tokens):
                end = min(start + self.chunk_size_tokens, len(tokens))
                chunks.append(self.tokenizer.decode(tokens[start:end]))
                start += self.chunk_size_tokens - self.chunk_overlap_tokens
            return chunks

        separator = separators[0]
        remaining_separators = separators[1:]

        # Split on the current separator
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        chunks: List[str] = []
        current_doc: List[str] = []
        current_tokens = 0

        for s in splits:
            if not s:
                continue

            piece = s + separator if separator else s
            piece_tokens = self.count_tokens(piece)

            if piece_tokens > self.chunk_size_tokens:
                # Piece itself is too large, recurse with finer separators
                if current_doc:
                    chunks.append("".join(current_doc).strip())
                    current_doc = []
                    current_tokens = 0

                sub_chunks = self._split_text_recursively(s, remaining_separators)
                chunks.extend(sub_chunks)
                continue

            if current_tokens + piece_tokens <= self.chunk_size_tokens:
                current_doc.append(piece)
                current_tokens += piece_tokens
            else:
                if current_doc:
                    full_chunk = "".join(current_doc).strip()
                    chunks.append(full_chunk)

                    # Build sliding window overlap
                    overlap_doc: List[str] = []
                    overlap_tokens = 0
                    for prev_piece in reversed(current_doc):
                        p_tok = self.count_tokens(prev_piece)
                        if overlap_tokens + p_tok <= self.chunk_overlap_tokens:
                            overlap_doc.insert(0, prev_piece)
                            overlap_tokens += p_tok
                        else:
                            break
                    current_doc = overlap_doc
                    current_tokens = overlap_tokens

                current_doc.append(piece)
                current_tokens += piece_tokens

        if current_doc:
            final_chunk = "".join(current_doc).strip()
            if final_chunk:
                chunks.append(final_chunk)

        return chunks

    def _chunk_table_respecting_headers(self, table_markdown: str) -> List[str]:
        """Chunks large Markdown tables row-by-row, repeating headers on continuation chunks."""
        lines = [l.strip() for l in table_markdown.split("\n") if l.strip()]
        if len(lines) < 2:
            return self._split_text_recursively(table_markdown, self.separators)

        header_lines = lines[:2]  # Header row and delimiter row (| --- | --- |)
        header_text = "\n".join(header_lines)
        header_tokens = self.count_tokens(header_text)

        data_rows = lines[2:]
        if not data_rows:
            return [table_markdown]

        chunks: List[str] = []
        current_rows: List[str] = []
        current_tokens = header_tokens

        for row in data_rows:
            row_tokens = self.count_tokens(row) + 1  # +1 for newline
            if current_tokens + row_tokens <= self.chunk_size_tokens:
                current_rows.append(row)
                current_tokens += row_tokens
            else:
                if current_rows:
                    chunk_text = header_text + "\n" + "\n".join(current_rows)
                    chunks.append(chunk_text)
                    current_rows = []
                    current_tokens = header_tokens
                current_rows.append(row)
                current_tokens += row_tokens

        if current_rows:
            chunks.append(header_text + "\n" + "\n".join(current_rows))

        return chunks

    def chunk_document(
        self,
        document: ExtractedDocument,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> List[DocumentChunkData]:
        """Transforms an ExtractedDocument into an ordered list of DocumentChunkData."""
        all_chunks: List[DocumentChunkData] = []
        chunk_idx = 0

        # If document has explicit pages, chunk page-by-page to maintain page numbers
        if document.pages:
            for page in document.pages:
                page_text = page.text.strip()
                if not page_text:
                    continue

                # Check if page is an isolated table or contains Markdown tables
                has_table_block = "| --- |" in page_text or "|:---|:" in page_text

                raw_chunks = self._split_text_recursively(page_text, self.separators)

                for chunk_text in raw_chunks:
                    clean_chunk = chunk_text.strip()
                    if not clean_chunk:
                        continue

                    tok_count = self.count_tokens(clean_chunk)
                    meta = ChunkMetadata(
                        document_id=document_id,
                        version_id=version_id,
                        organization_id=organization_id,
                        chunk_index=chunk_idx,
                        page_number=page.page_number,
                        token_count=tok_count,
                        char_count=len(clean_chunk),
                        has_table=has_table_block and ("|" in clean_chunk),
                    )
                    all_chunks.append(
                        DocumentChunkData(
                            content=clean_chunk,
                            metadata=meta,
                            embedding=None,
                        )
                    )
                    chunk_idx += 1
        else:
            # Single continuous flow
            raw_chunks = self._split_text_recursively(document.full_text, self.separators)
            for chunk_text in raw_chunks:
                clean_chunk = chunk_text.strip()
                if not clean_chunk:
                    continue

                tok_count = self.count_tokens(clean_chunk)
                meta = ChunkMetadata(
                    document_id=document_id,
                    version_id=version_id,
                    organization_id=organization_id,
                    chunk_index=chunk_idx,
                    page_number=1,
                    token_count=tok_count,
                    char_count=len(clean_chunk),
                    has_table=("| --- |" in clean_chunk or "|:---" in clean_chunk),
                )
                all_chunks.append(
                    DocumentChunkData(
                        content=clean_chunk,
                        metadata=meta,
                        embedding=None,
                    )
                )
                chunk_idx += 1

        logger.info(
            f"Chunked document '{document_id}' ({document.file_name}) into "
            f"{len(all_chunks)} chunks (avg tokens: "
            f"{sum(c.metadata.token_count for c in all_chunks) / max(len(all_chunks), 1):.1f})"
        )
        return all_chunks

    def calculate_statistics(self, chunks: List[DocumentChunkData]) -> ChunkingStatistics:
        """Calculates descriptive summary metrics over a collection of chunks."""
        if not chunks:
            return ChunkingStatistics(
                total_chunks=0,
                total_tokens=0,
                average_tokens_per_chunk=0.0,
                max_tokens=0,
                min_tokens=0,
                chunks_with_tables=0,
            )

        token_counts = [c.metadata.token_count for c in chunks]
        total_tokens = sum(token_counts)
        table_chunks = sum(1 for c in chunks if c.metadata.has_table)

        return ChunkingStatistics(
            total_chunks=len(chunks),
            total_tokens=total_tokens,
            average_tokens_per_chunk=total_tokens / len(chunks),
            max_tokens=max(token_counts),
            min_tokens=min(token_counts),
            chunks_with_tables=table_chunks,
        )
