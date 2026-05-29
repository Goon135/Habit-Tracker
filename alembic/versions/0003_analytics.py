"""add recovery mode and insight tracking

Revision ID: 0003_analytics
Revises: 0002_personalization
Create Date: 2026-05-26 00:00:00.000000

Добавлено:
- users.recovery_until, users.recovery_started_at — состояние recovery mode (#3).
- users.last_insight_at — ratelimit для /insights, чтобы не звать LLM каждую минуту.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_analytics"
down_revision: Union[str, None] = "0002_personalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("recovery_until", sa.Date(), nullable=True))
        batch.add_column(sa.Column("recovery_started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_insight_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_insight_at")
        batch.drop_column("recovery_started_at")
        batch.drop_column("recovery_until")
