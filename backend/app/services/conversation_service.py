import logging
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException, ForbiddenException
from app.models.citation import MessageCitation
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.chat import (
    CitationResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
)

logger = logging.getLogger("enterprise_rag.conversation_service")


class ConversationService:
    """Service managing multi-turn chat sessions, message persistence, and citation mapping."""

    @staticmethod
    async def create_conversation(
        session: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        title: Optional[str] = None,
    ) -> Conversation:
        """Initializes a new conversation session for a user."""
        conv_title = title.strip() if title and title.strip() else "New Conversation"
        conv = Conversation(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            title=conv_title,
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        logger.info(f"Created conversation '{conv.id}' for user {user_id} (tenant {organization_id}).")
        return conv

    @staticmethod
    async def get_conversation(
        session: AsyncSession,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Conversation:
        """Fetches a conversation with its messages and citations loaded."""
        stmt = (
            select(Conversation)
            .options(
                selectinload(Conversation.messages)
                .selectinload(Message.citations)
                .selectinload(MessageCitation.chunk),
            )
            .where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()

        if not conv:
            raise EntityNotFoundException("Conversation", conversation_id)

        # Enforce user boundary if supplied
        if user_id and conv.user_id != user_id:
            raise ForbiddenException("You do not have access to this conversation.")

        return conv

    @staticmethod
    async def list_conversations(
        session: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConversationResponse]:
        """Lists active conversations for the authenticated user."""
        stmt = (
            select(
                Conversation,
                func.count(Message.id).label("message_count"),
            )
            .outerjoin(Message, Conversation.id == Message.conversation_id)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.user_id == user_id,
                Conversation.is_archived.is_(False),
            )
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        rows = result.all()

        conversations = []
        for conv, count in rows:
            conversations.append(
                ConversationResponse(
                    id=conv.id,
                    organization_id=conv.organization_id,
                    user_id=conv.user_id,
                    title=conv.title,
                    is_archived=conv.is_archived,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=count,
                )
            )
        return conversations

    @staticmethod
    async def add_message(
        session: AsyncSession,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        model_parameters: Optional[Dict[str, Any]] = None,
        citations: Optional[List[CitationResponse]] = None,
    ) -> Message:
        """Persists a message and its source citations in PostgreSQL."""
        msg = Message(
            id=uuid.uuid4(),
            organization_id=organization_id,
            conversation_id=conversation_id,
            role=role.upper(),
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            model_parameters=model_parameters or {},
        )
        session.add(msg)
        await session.flush()

        if citations:
            citation_models = []
            for c in citations:
                citation_record = MessageCitation(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    message_id=msg.id,
                    chunk_id=c.chunk_id,
                    relevance_score=c.relevance_score,
                    rank_position=c.rank_position,
                    snippet=c.snippet,
                )
                citation_models.append(citation_record)
            session.add_all(citation_models)

        # Update parent conversation updated_at timestamp
        conv = await session.get(Conversation, conversation_id)
        if conv:
            # If conversation has default title and this is user message, generate title from prompt
            if conv.title == "New Conversation" and role.upper() == "USER":
                conv.title = content[:50].strip() + ("..." if len(content) > 50 else "")

        await session.commit()
        await session.refresh(msg)
        return msg

    @classmethod
    def serialize_conversation_detail(cls, conv: Conversation) -> ConversationDetailResponse:
        """Converts ORM Conversation and Message tree into Pydantic schema."""
        messages: List[MessageResponse] = []
        for m in conv.messages:
            cits: List[CitationResponse] = []
            for c in m.citations:
                cits.append(
                    CitationResponse(
                        chunk_id=c.chunk_id,
                        document_id=c.chunk.document_id if c.chunk else uuid.UUID(int=0),
                        rank_position=c.rank_position,
                        relevance_score=c.relevance_score,
                        snippet=c.snippet,
                    )
                )
            messages.append(
                MessageResponse(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                    citations=cits,
                )
            )

        return ConversationDetailResponse(
            id=conv.id,
            organization_id=conv.organization_id,
            user_id=conv.user_id,
            title=conv.title,
            is_archived=conv.is_archived,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            messages=messages,
        )
