"""initial_business_schema

Revision ID: 7180b5fa6dc0
Revises: 
Create Date: 2026-11-14 22:30:20.292988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '7180b5fa6dc0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table('organizations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)
    op.create_table('departments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'code', name='uq_departments_org_code'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_departments_org_id')
    )
    op.create_index(op.f('ix_departments_organization_id'), 'departments', ['organization_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('department_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'email', name='uq_users_org_email'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_users_org_id')
    )
    op.create_index(op.f('ix_users_department_id'), 'users', ['department_id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_organization_id'), 'users', ['organization_id'], unique=False)
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_conversations_org_id')
    )
    op.create_index(op.f('ix_conversations_organization_id'), 'conversations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('department_id', sa.UUID(), nullable=True),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('file_type', sa.String(length=50), nullable=False),
    sa.Column('file_hash', sa.String(length=64), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('current_version_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("file_type IN ('PDF', 'DOCX', 'TXT')", name='chk_documents_file_type'),
    sa.CheckConstraint("status IN ('PENDING', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED')", name='chk_documents_status'),
    sa.CheckConstraint('file_size_bytes > 0', name='chk_documents_size_positive'),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'file_hash', name='uq_documents_org_file_hash'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_documents_org_id')
    )
    op.create_index(op.f('ix_documents_department_id'), 'documents', ['department_id'], unique=False)
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)
    op.create_table('document_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('file_hash', sa.String(length=64), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('change_summary', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'document_id'], ['documents.organization_id', 'documents.id'], name='fk_doc_versions_org_document', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'version_number', name='uq_doc_version_number'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_doc_versions_org_id')
    )
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_versions_is_active'), 'document_versions', ['is_active'], unique=False)
    op.create_index(op.f('ix_document_versions_organization_id'), 'document_versions', ['organization_id'], unique=False)
    op.create_table('ingestion_jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('max_retries', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('progress_percent', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.String(length=100), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED', 'CANCELLED')", name='chk_jobs_status'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'document_id'], ['documents.organization_id', 'documents.id'], name='fk_jobs_org_document', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_jobs_org_id'),
    sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_jobs_org_idempotency')
    )
    op.create_index(op.f('ix_ingestion_jobs_document_id'), 'ingestion_jobs', ['document_id'], unique=False)
    op.create_index(op.f('ix_ingestion_jobs_organization_id'), 'ingestion_jobs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_ingestion_jobs_status'), 'ingestion_jobs', ['status'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('model_parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'conversation_id'], ['conversations.organization_id', 'conversations.id'], name='fk_messages_org_conversation', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_messages_org_id')
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_organization_id'), 'messages', ['organization_id'], unique=False)
    op.create_table('document_chunks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', content)", persisted=True), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'document_id'], ['documents.organization_id', 'documents.id'], name='fk_chunks_org_document', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'version_id'], ['document_versions.organization_id', 'document_versions.id'], name='fk_chunks_org_version', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['document_versions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_chunks_org_id'),
    sa.UniqueConstraint('version_id', 'chunk_index', name='uq_chunks_version_index')
    )
    op.create_index('idx_chunks_embedding_hnsw', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('idx_chunks_org_active', 'document_chunks', ['organization_id', 'is_active'], unique=False)
    op.create_index('idx_chunks_org_doc_version', 'document_chunks', ['organization_id', 'document_id', 'version_id'], unique=False)
    op.create_index('idx_chunks_search_vector', 'document_chunks', ['search_vector'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_organization_id'), 'document_chunks', ['organization_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_version_id'), 'document_chunks', ['version_id'], unique=False)
    op.create_table('feedback',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('message_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=False),
    sa.Column('feedback_text', sa.Text(), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('rating IN (1, -1)', name='chk_feedback_rating_values'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'message_id'], ['messages.organization_id', 'messages.id'], name='fk_feedback_org_message', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_feedback_org_id'),
    sa.UniqueConstraint('user_id', 'message_id', name='uq_user_message_feedback')
    )
    op.create_index(op.f('ix_feedback_message_id'), 'feedback', ['message_id'], unique=False)
    op.create_index(op.f('ix_feedback_organization_id'), 'feedback', ['organization_id'], unique=False)
    op.create_index(op.f('ix_feedback_user_id'), 'feedback', ['user_id'], unique=False)
    op.create_table('message_citations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('message_id', sa.UUID(), nullable=False),
    sa.Column('chunk_id', sa.UUID(), nullable=False),
    sa.Column('relevance_score', sa.Float(), nullable=False),
    sa.Column('rank_position', sa.Integer(), nullable=False),
    sa.Column('snippet', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'chunk_id'], ['document_chunks.organization_id', 'document_chunks.id'], name='fk_citations_org_chunk', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'message_id'], ['messages.organization_id', 'messages.id'], name='fk_citations_org_message', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_citations_org_id')
    )
    op.create_index(op.f('ix_message_citations_chunk_id'), 'message_citations', ['chunk_id'], unique=False)
    op.create_index(op.f('ix_message_citations_message_id'), 'message_citations', ['message_id'], unique=False)
    op.create_index(op.f('ix_message_citations_organization_id'), 'message_citations', ['organization_id'], unique=False)
    
    # 2. Enable PostgreSQL Row Level Security (RLS) on tenant-scoped tables
    rls_tables = [
        "documents",
        "document_versions",
        "document_chunks",
        "conversations",
        "messages",
        "message_citations",
        "feedback",
        "ingestion_jobs",
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY rls_{table}_tenant_isolation ON {table}
            FOR ALL
            USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)
        # Grant DML permissions to the application role
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO rag_app_user;")
    
    # Also grant base access to organizations, departments, users
    for base_table in ["organizations", "departments", "users"]:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {base_table} TO rag_app_user;")


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_message_citations_organization_id'), table_name='message_citations')
    op.drop_index(op.f('ix_message_citations_message_id'), table_name='message_citations')
    op.drop_index(op.f('ix_message_citations_chunk_id'), table_name='message_citations')
    op.drop_table('message_citations')
    op.drop_index(op.f('ix_feedback_user_id'), table_name='feedback')
    op.drop_index(op.f('ix_feedback_organization_id'), table_name='feedback')
    op.drop_index(op.f('ix_feedback_message_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_document_chunks_version_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_organization_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_index('idx_chunks_search_vector', table_name='document_chunks', postgresql_using='gin')
    op.drop_index('idx_chunks_org_doc_version', table_name='document_chunks')
    op.drop_index('idx_chunks_org_active', table_name='document_chunks')
    op.drop_index('idx_chunks_embedding_hnsw', table_name='document_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('document_chunks')
    op.drop_index(op.f('ix_messages_organization_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_ingestion_jobs_status'), table_name='ingestion_jobs')
    op.drop_index(op.f('ix_ingestion_jobs_organization_id'), table_name='ingestion_jobs')
    op.drop_index(op.f('ix_ingestion_jobs_document_id'), table_name='ingestion_jobs')
    op.drop_table('ingestion_jobs')
    op.drop_index(op.f('ix_document_versions_organization_id'), table_name='document_versions')
    op.drop_index(op.f('ix_document_versions_is_active'), table_name='document_versions')
    op.drop_index(op.f('ix_document_versions_document_id'), table_name='document_versions')
    op.drop_table('document_versions')
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_department_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_organization_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_users_organization_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_department_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_departments_organization_id'), table_name='departments')
    op.drop_table('departments')
    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_table('organizations')
    # ### end Alembic commands ###
