import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
)
from app.services.conversation_service import ConversationService
from app.services.rag_service import RAGService

logger = logging.getLogger("enterprise_rag.chat_api")

router = APIRouter()


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Chat Conversation",
    description="Initializes a new multi-turn conversation session.",
)
async def create_conversation(
    request: ConversationCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.CHAT_QUERY)),
) -> ConversationResponse:
    conv = await ConversationService.create_conversation(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        title=request.title,
    )
    return ConversationResponse(
        id=conv.id,
        organization_id=conv.organization_id,
        user_id=conv.user_id,
        title=conv.title,
        is_archived=conv.is_archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get(
    "/conversations",
    response_model=List[ConversationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Conversations",
    description="Lists chat conversations for the current user.",
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.CHAT_QUERY)),
) -> List[ConversationResponse]:
    return await ConversationService.list_conversations(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Conversation Detail",
    description="Retrieves a conversation including all message history and verifiable citations.",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.CHAT_QUERY)),
) -> ConversationDetailResponse:
    conv = await ConversationService.get_conversation(
        session=session,
        organization_id=current_user.organization_id,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    return ConversationService.serialize_conversation_detail(conv)


@router.post(
    "/completions",
    summary="RAG Chat Completion (Streaming & Non-Streaming)",
    description="Executes grounded retrieval-augmented chat completion with verifiable bracket citations.",
)
async def chat_completion(
    request: ChatCompletionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.CHAT_QUERY)),
):
    rag_service = RAGService()

    if request.stream:
        return StreamingResponse(
            rag_service.stream_chat_completion(
                session=session,
                current_user=current_user,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        return await rag_service.generate_chat_completion(
            session=session,
            current_user=current_user,
            request=request,
        )
