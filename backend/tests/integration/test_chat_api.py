import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token, get_password_hash
from app.models.citation import MessageCitation
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.message import Message
from app.models.organization import Organization
from app.models.user import User
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkMetadata, DocumentChunkData
from app.services.embedding_service import EmbeddingService

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
async def setup_chat_tenants():
    """Seeds test organizations, users, documents, and chunks for RAG chat testing."""
    embedder = EmbeddingService(api_key=None, dimensions=1536)

    async with SessionLocal() as session:
        # Org Alpha
        org_a = Organization(
            id=uuid.uuid4(),
            name="Chat Alpha Corp",
            slug=f"chat-a-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        # Org Beta
        org_b = Organization(
            id=uuid.uuid4(),
            name="Chat Beta Corp",
            slug=f"chat-b-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add_all([org_a, org_b])
        await session.flush()

        pw_hash = get_password_hash("ChatPass123!")
        user_a = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"alice-{uuid.uuid4().hex[:4]}@chat-a.com",
            hashed_password=pw_hash,
            full_name="Alice Chat",
            role="EMPLOYEE",
            is_active=True,
        )
        user_b = User(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            email=f"bob-{uuid.uuid4().hex[:4]}@chat-b.com",
            hashed_password=pw_hash,
            full_name="Bob Chat",
            role="EMPLOYEE",
            is_active=True,
        )
        session.add_all([user_a, user_b])
        await session.flush()

        # Document: Remote Work Policy
        doc_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            organization_id=org_a.id,
            uploaded_by_id=user_a.id,
            title="Remote Work & Core Hours Policy",
            file_name="remote_policy.pdf",
            file_path="storage/remote_policy.pdf",
            file_type="PDF",
            file_size_bytes=1024,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="COMPLETED",
            current_version_id=ver_id,
        )
        ver = DocumentVersion(
            id=ver_id,
            organization_id=org_a.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=1024,
            file_hash=doc.file_hash,
            file_path=doc.file_path,
            created_by_id=user_a.id,
            is_active=True,
        )
        session.add_all([doc, ver])
        await session.flush()

        text_content = (
            "Employees may work remotely up to three days per week with manager approval. "
            "Mandatory core collaboration hours are between 10:00 AM and 3:00 PM Eastern Time."
        )
        chunks = [
            DocumentChunkData(
                content=text_content,
                embedding=embedder._generate_mock_vector(text_content),
                metadata=ChunkMetadata(
                    document_id=doc_id,
                    version_id=ver_id,
                    organization_id=org_a.id,
                    chunk_index=0,
                    page_number=1,
                    token_count=32,
                    char_count=len(text_content),
                    section_title="Remote Work Guidelines",
                ),
            )
        ]
        await VectorRepository.batch_insert_chunks(session, chunks)
        await session.commit()

        token_a = create_access_token(
            user_id=str(user_a.id),
            organization_id=str(org_a.id),
            organization_slug=org_a.slug,
            role=user_a.role,
        )
        token_b = create_access_token(
            user_id=str(user_b.id),
            organization_id=str(org_b.id),
            organization_slug=org_b.slug,
            role=user_b.role,
        )

        return {
            "org_a": org_a,
            "org_b": org_b,
            "user_a": user_a,
            "user_b": user_b,
            "token_a": token_a,
            "token_b": token_b,
            "doc_id": doc_id,
        }


@pytest.mark.asyncio
async def test_create_and_list_conversations(async_client: AsyncClient, setup_chat_tenants):
    """1. Test creating and listing conversations."""
    data = setup_chat_tenants
    token_a = data["token_a"]

    # Create Conversation
    create_resp = await async_client.post(
        "/api/v1/chat/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Policy Inquiries"},
    )
    assert create_resp.status_code == 201
    conv_data = create_resp.json()
    assert conv_data["title"] == "Policy Inquiries"
    conv_id = conv_data["id"]

    # List Conversations
    list_resp = await async_client.get(
        "/api/v1/chat/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    conversations = list_resp.json()
    assert len(conversations) >= 1
    assert any(c["id"] == conv_id for c in conversations)


@pytest.mark.asyncio
async def test_non_streaming_chat_completion(async_client: AsyncClient, setup_chat_tenants):
    """2. Test synchronous RAG chat completion with citations and database persistence."""
    data = setup_chat_tenants
    token_a = data["token_a"]

    resp = await async_client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "message": "Employees may work remotely up to three days per week with manager approval.",
            "stream": False,
            "retrieval_method": "HYBRID",
            "retrieval_limit": 3,
        },
    )

    assert resp.status_code == 200
    body = resp.json()

    assert body["role"] == "ASSISTANT"
    assert len(body["content"]) > 10
    assert len(body["citations"]) >= 1
    assert body["tokens_used"] > 0
    assert body["latency_ms"] > 0

    conv_id = body["conversation_id"]
    msg_id = body["message_id"]

    # Verify citation fields
    citation = body["citations"][0]
    assert citation["rank_position"] == 1
    assert "work remotely" in citation["snippet"]

    # Verify Database Persistence
    async with SessionLocal() as session:
        # Check message
        stmt = select(Message).where(Message.id == uuid.UUID(msg_id))
        res = await session.execute(stmt)
        msg_db = res.scalar_one()
        assert msg_db.conversation_id == uuid.UUID(conv_id)
        assert msg_db.role == "ASSISTANT"

        # Check citations
        cit_stmt = select(MessageCitation).where(MessageCitation.message_id == msg_db.id)
        cit_res = await session.execute(cit_stmt)
        db_citations = list(cit_res.scalars().all())
        assert len(db_citations) >= 1
        assert "work remotely" in db_citations[0].snippet


@pytest.mark.asyncio
async def test_streaming_chat_completion_sse(async_client: AsyncClient, setup_chat_tenants):
    """3. Test Server-Sent Events (SSE) streaming chat completion."""
    data = setup_chat_tenants
    token_a = data["token_a"]

    resp = await async_client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "message": "Mandatory core collaboration hours are between 10:00 AM and 3:00 PM Eastern Time.",
            "stream": True,
            "retrieval_method": "HYBRID",
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    raw_sse_lines = resp.text.split("\n\n")
    events = []
    for block in raw_sse_lines:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_name = lines[0].replace("event: ", "").strip()
        data_str = lines[1].replace("data: ", "").strip()
        events.append((event_name, json.loads(data_str)))

    # Must contain token events, citations event, and done event
    event_names = [e[0] for e in events]
    assert "token" in event_names
    assert "citations" in event_names
    assert "done" in event_names

    # Check citations payload
    citation_event = next(e for e in events if e[0] == "citations")
    assert len(citation_event[1]["citations"]) >= 1

    # Check done payload
    done_event = next(e for e in events if e[0] == "done")
    assert "conversation_id" in done_event[1]
    assert "message_id" in done_event[1]


@pytest.mark.asyncio
async def test_multi_turn_conversation_history(async_client: AsyncClient, setup_chat_tenants):
    """4. Test multi-turn conversation retains sequential history and updates message counts."""
    data = setup_chat_tenants
    token_a = data["token_a"]

    # Turn 1
    resp1 = await async_client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "message": "What are our remote work hours?",
            "stream": False,
        },
    )
    assert resp1.status_code == 200
    conv_id = resp1.json()["conversation_id"]

    # Turn 2: Continue in same conversation
    resp2 = await async_client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "conversation_id": conv_id,
            "message": "Do I need manager approval?",
            "stream": False,
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == conv_id

    # Fetch Conversation Detail
    detail_resp = await async_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    # Total 4 messages: Turn 1 User + Asst, Turn 2 User + Asst
    assert len(detail["messages"]) == 4
    assert detail["messages"][0]["role"] == "USER"
    assert detail["messages"][1]["role"] == "ASSISTANT"
    assert detail["messages"][2]["role"] == "USER"
    assert detail["messages"][3]["role"] == "ASSISTANT"


@pytest.mark.asyncio
async def test_chat_cross_tenant_isolation(async_client: AsyncClient, setup_chat_tenants):
    """5. Test User Beta cannot access User Alpha's conversation."""
    data = setup_chat_tenants
    token_a = data["token_a"]
    token_b = data["token_b"]

    # User Alpha creates conversation
    create_resp = await async_client.post(
        "/api/v1/chat/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Alpha Confidential Session"},
    )
    conv_id = create_resp.json()["id"]

    # User Beta attempts to read User Alpha's conversation -> MUST return 404 or 403
    forbidden_resp = await async_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_resp.status_code in (403, 404)
