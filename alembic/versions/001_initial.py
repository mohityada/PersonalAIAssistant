"""Initial migration — create users, files, chunks tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("api_key_hash", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Files
    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("file_type", sa.String(20), nullable=False, index=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("objects", JSON, nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("tags", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Chunks
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id"), nullable=False, index=True),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("vector_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("files")
    op.drop_table("users")
