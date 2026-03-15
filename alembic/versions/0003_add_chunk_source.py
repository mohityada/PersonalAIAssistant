"""add chunk source column

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_chunk_source"
down_revision: Union[str, None] = "0002_add_file_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("source", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "source")
