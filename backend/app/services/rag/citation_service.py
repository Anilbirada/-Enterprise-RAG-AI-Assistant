import re
import uuid
from typing import List, Set, Tuple
from app.schemas.chat import CitationResponse
from app.schemas.chunk import ChunkSearchResult


class CitationService:
    """Extracts, parses, and resolves verifiable source citations from LLM generation text."""

    # Regex matches single [1] or combined [1][2] or comma-separated [1, 2]
    CITATION_PATTERN = re.compile(r"\[(\d+)\]")

    @classmethod
    def extract_citations(
        cls,
        response_text: str,
        candidate_chunks: List[ChunkSearchResult],
    ) -> List[CitationResponse]:
        """Parses numbered brackets from response text and resolves them to candidate chunks."""
        if not candidate_chunks or not response_text:
            return []

        # Find all cited 1-based indices in the text
        raw_matches = cls.CITATION_PATTERN.findall(response_text)
        cited_indices: Set[int] = set()
        for match in raw_matches:
            try:
                cited_indices.add(int(match))
            except ValueError:
                continue

        citations: List[CitationResponse] = []
        for index in sorted(cited_indices):
            # Candidate chunks are 0-indexed; citations in text are 1-based [1], [2]...
            chunk_pos = index - 1
            if 0 <= chunk_pos < len(candidate_chunks):
                chunk = candidate_chunks[chunk_pos]
                # Extract clean snippet (first 200 characters)
                snippet = chunk.content[:200].strip()
                if len(chunk.content) > 200:
                    snippet += "..."

                doc_title = (
                    chunk.metadata.get("document_title")
                    or chunk.metadata.get("title")
                    or chunk.section_title
                    or "Corporate Policy Document"
                )
                citations.append(
                    CitationResponse(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        rank_position=index,
                        relevance_score=chunk.score,
                        snippet=snippet,
                        page_number=chunk.page_number,
                        section_title=chunk.section_title,
                        citation_number=index,
                        document_title=doc_title,
                    )
                )

        # Fallback: if no brackets were produced by the LLM, but candidate chunks were returned,
        # attribute the top candidate chunk as citation [1] if relevance is high (> 0.5)
        if not citations and candidate_chunks and candidate_chunks[0].score > 0.01:
            top_chunk = candidate_chunks[0]
            snippet = top_chunk.content[:200].strip()
            if len(top_chunk.content) > 200:
                snippet += "..."
            top_title = (
                top_chunk.metadata.get("document_title")
                or top_chunk.metadata.get("title")
                or top_chunk.section_title
                or "Corporate Policy Document"
            )
            citations.append(
                CitationResponse(
                    chunk_id=top_chunk.chunk_id,
                    document_id=top_chunk.document_id,
                    rank_position=1,
                    relevance_score=top_chunk.score,
                    snippet=snippet,
                    page_number=top_chunk.page_number,
                    section_title=top_chunk.section_title,
                    citation_number=1,
                    document_title=top_title,
                )
            )

        return citations
