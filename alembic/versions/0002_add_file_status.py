"""Add status and error_message columns to files table.

Revision ID: 0002_add_file_status
Revises: 0166ad5eb5c8
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_file_status"
down_revision: Union[str, None] = "0166ad5eb5c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="processing",
        ),
    )
    op.add_column(
        "files",
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_files_status", "files", ["status"])


def downgrade() -> None:
    op.drop_index("ix_files_status", table_name="files")
    op.drop_column("files", "error_message")
    op.drop_column("files", "status")
