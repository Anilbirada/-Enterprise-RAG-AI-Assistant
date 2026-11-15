"""update_document_and_job_status_constraints

Revision ID: c3d4e5f6a7b8
Revises: b2c34c8974ee
Create Date: 2026-11-15 10:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c34c8974ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update documents status constraint to include 'UPLOADED'
    op.drop_constraint('chk_documents_status', 'documents', type_='check')
    op.create_check_constraint(
        'chk_documents_status',
        'documents',
        "status IN ('PENDING', 'UPLOADED', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED')"
    )

    # 2. Update ingestion_jobs status constraint to include 'QUEUED' and 'PROCESSING'
    op.drop_constraint('chk_jobs_status', 'ingestion_jobs', type_='check')
    op.create_check_constraint(
        'chk_jobs_status',
        'ingestion_jobs',
        "status IN ('PENDING', 'QUEUED', 'PROCESSING', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED', 'CANCELLED')"
    )


def downgrade() -> None:
    # Revert ingestion_jobs status constraint
    op.drop_constraint('chk_jobs_status', 'ingestion_jobs', type_='check')
    op.create_check_constraint(
        'chk_jobs_status',
        'ingestion_jobs',
        "status IN ('PENDING', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED', 'CANCELLED')"
    )

    # Revert documents status constraint
    op.drop_constraint('chk_documents_status', 'documents', type_='check')
    op.create_check_constraint(
        'chk_documents_status',
        'documents',
        "status IN ('PENDING', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED')"
    )
