import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ExternalServiceException
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CitationResponse,
)
from app.schemas.chunk import ChunkSearchResult
from app.schemas.search import HybridSearchRequest, SemanticSearchRequest
from app.services.conversation_service import ConversationService
from app.services.hybrid_search_service import HybridSearchService
from app.services.rag.citation_service import CitationService
from app.services.rag.prompt_templates import build_rag_messages

logger = logging.getLogger("enterprise_rag.rag_service")


class RAGService:
    """Service orchestrating document retrieval, context synthesis, LLM streaming, and citation persistence."""

    def __init__(
        self,
        hybrid_search_service: Optional[HybridSearchService] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.search_service = hybrid_search_service or HybridSearchService()
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.LLM_MODEL
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def _get_conversation_history(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
        exclude_message_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, str]]:
        """Retrieves recent conversation turns safely via async query to avoid lazy loading."""
        stmt = (
            select(Message.role, Message.content)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        if exclude_message_id:
            stmt = stmt.where(Message.id != exclude_message_id)

        result = await session.execute(stmt)
        return [{"role": role, "content": content} for role, content in result.all()]

    async def _retrieve_context(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        request: ChatCompletionRequest,
    ) -> List[ChunkSearchResult]:
        """Retrieves top candidate chunks using hybrid or dense retrieval."""
        if request.retrieval_method == "DENSE":
            search_req = SemanticSearchRequest(
                query=request.message,
                limit=request.retrieval_limit,
                similarity_threshold=request.similarity_threshold,
                document_ids=request.document_ids,
                department_id=request.department_id,
            )
            resp = await self.search_service.search_semantic(session, organization_id, search_req)
        else:
            hybrid_req = HybridSearchRequest(
                query=request.message,
                limit=request.retrieval_limit,
                similarity_threshold=request.similarity_threshold,
                document_ids=request.document_ids,
                department_id=request.department_id,
            )
            resp = await self.search_service.search_hybrid(session, organization_id, hybrid_req)

        return resp.results

    async def _generate_mock_stream(
        self,
        query: str,
        context_chunks: List[ChunkSearchResult],
    ) -> AsyncGenerator[str, None]:
        """Generates deterministic simulated token stream for tests and offline development."""
        if not context_chunks:
            mock_text = (
                "I cannot find sufficient information in the provided corporate documents to answer your question."
            )
        else:
            top_chunk = context_chunks[0]
            mock_text = (
                f"Based on the corporate records, {top_chunk.content.strip()} [1]"
            )
            if len(context_chunks) > 1:
                mock_text += f" Furthermore, {context_chunks[1].content.strip()} [2]"

        words = mock_text.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            yield token
            # Yield control briefly
            await asyncio.sleep(0.005)

    async def stream_chat_completion(
        self,
        session: AsyncSession,
        current_user: User,
        request: ChatCompletionRequest,
    ) -> AsyncGenerator[str, None]:
        """Streams Server-Sent Events (SSE) tokens, citations, and completion metadata."""
        start_time = time.perf_counter()
        org_id = current_user.organization_id

        # 1. Resolve or create Conversation
        if request.conversation_id:
            conv = await ConversationService.get_conversation(
                session=session,
                organization_id=org_id,
                conversation_id=request.conversation_id,
                user_id=current_user.id,
            )
        else:
            conv = await ConversationService.create_conversation(
                session=session,
                organization_id=org_id,
                user_id=current_user.id,
                title=request.message[:40],
            )

        # 2. Persist user message in conversation history
        user_msg = await ConversationService.add_message(
            session=session,
            organization_id=org_id,
            conversation_id=conv.id,
            role="USER",
            content=request.message,
        )

        # 3. Retrieve grounding context chunks
        context_chunks = await self._retrieve_context(session, org_id, request)

        # 4. Load past messages for conversation context
        past_turns = await self._get_conversation_history(
            session=session,
            conversation_id=conv.id,
            exclude_message_id=user_msg.id,
        )
        prompt_messages = build_rag_messages(
            query=request.message,
            context_chunks=context_chunks,
            conversation_history=past_turns,
        )

        # 5. Stream LLM tokens
        full_response_text = ""
        prompt_tokens_est = sum(len(m["content"].split()) for m in prompt_messages)
        completion_tokens_est = 0

        try:
            if self.client:
                # Live OpenAI stream
                response_stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=prompt_messages,
                    temperature=0.2,
                    stream=True,
                )
                async for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response_text += token
                        completion_tokens_est += 1
                        event_payload = json.dumps({"token": token})
                        yield f"event: token\ndata: {event_payload}\n\n"
            else:
                # Offline deterministic mock stream
                async for token in self._generate_mock_stream(request.message, context_chunks):
                    full_response_text += token
                    completion_tokens_est += 1
                    event_payload = json.dumps({"token": token})
                    yield f"event: token\ndata: {event_payload}\n\n"

        except Exception as exc:
            logger.error(f"Error during LLM streaming: {exc}", exc_info=True)
            err_payload = json.dumps({"error": str(exc)})
            yield f"event: error\ndata: {err_payload}\n\n"
            return

        # 6. Parse and resolve verifiable citations
        citations = CitationService.extract_citations(
            response_text=full_response_text,
            candidate_chunks=context_chunks,
        )

        # Emit citations event
        citation_payload = json.dumps({
            "citations": [c.model_dump(mode="json") for c in citations]
        })
        yield f"event: citations\ndata: {citation_payload}\n\n"

        # 7. Persist assistant message and citations in PostgreSQL
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        asst_msg = await ConversationService.add_message(
            session=session,
            organization_id=org_id,
            conversation_id=conv.id,
            role="ASSISTANT",
            content=full_response_text,
            prompt_tokens=prompt_tokens_est,
            completion_tokens=completion_tokens_est,
            latency_ms=round(latency_ms, 2),
            model_parameters={"model": self.model, "temperature": 0.2},
            citations=citations,
        )

        # 8. Emit final done event
        done_payload = json.dumps({
            "conversation_id": str(conv.id),
            "message_id": str(asst_msg.id),
            "latency_ms": round(latency_ms, 2),
        })
        yield f"event: done\ndata: {done_payload}\n\n"

    async def generate_chat_completion(
        self,
        session: AsyncSession,
        current_user: User,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """Executes non-streaming synchronous chat completion."""
        start_time = time.perf_counter()
        org_id = current_user.organization_id

        # 1. Resolve or create Conversation
        if request.conversation_id:
            conv = await ConversationService.get_conversation(
                session=session,
                organization_id=org_id,
                conversation_id=request.conversation_id,
                user_id=current_user.id,
            )
        else:
            conv = await ConversationService.create_conversation(
                session=session,
                organization_id=org_id,
                user_id=current_user.id,
                title=request.message[:40],
            )

        # 2. Persist user message
        user_msg = await ConversationService.add_message(
            session=session,
            organization_id=org_id,
            conversation_id=conv.id,
            role="USER",
            content=request.message,
        )

        # 3. Retrieve context chunks
        context_chunks = await self._retrieve_context(session, org_id, request)

        # 4. Build prompt
        past_turns = await self._get_conversation_history(
            session=session,
            conversation_id=conv.id,
            exclude_message_id=user_msg.id,
        )
        prompt_messages = build_rag_messages(
            query=request.message,
            context_chunks=context_chunks,
            conversation_history=past_turns,
        )

        # 5. Call LLM
        prompt_tokens_est = sum(len(m["content"].split()) for m in prompt_messages)
        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=prompt_messages,
                    temperature=0.2,
                )
                full_text = response.choices[0].message.content or ""
                completion_tokens = response.usage.completion_tokens if response.usage else len(full_text.split())
            except Exception as exc:
                raise ExternalServiceException("OpenAI Chat API", str(exc))
        else:
            # Offline mock
            full_text = ""
            async for token in self._generate_mock_stream(request.message, context_chunks):
                full_text += token
            completion_tokens = len(full_text.split())

        # 6. Extract citations
        citations = CitationService.extract_citations(
            response_text=full_text,
            candidate_chunks=context_chunks,
        )

        # 7. Persist assistant message
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        asst_msg = await ConversationService.add_message(
            session=session,
            organization_id=org_id,
            conversation_id=conv.id,
            role="ASSISTANT",
            content=full_text,
            prompt_tokens=prompt_tokens_est,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 2),
            model_parameters={"model": self.model, "temperature": 0.2},
            citations=citations,
        )

        return ChatCompletionResponse(
            conversation_id=conv.id,
            message_id=asst_msg.id,
            role="ASSISTANT",
            content=full_text,
            citations=citations,
            tokens_used=prompt_tokens_est + completion_tokens,
            latency_ms=round(latency_ms, 2),
        )
