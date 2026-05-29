"""add personalization, quantitative habits, goals, memory

Revision ID: 0002_personalization
Revises: 0001_initial
Create Date: 2026-05-25 00:00:00.000000

Добавлено:
- users: motivation_style, priority_focus, onboarding_completed,
         memory_summary, memory_updated_at
- habits: target_value, unit, is_goal, end_date
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_personalization"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: персонализация + memory
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column(
            "motivation_style", sa.String(32), nullable=False, server_default="not_set",
        ))
        batch.add_column(sa.Column(
            "priority_focus", sa.String(32), nullable=False, server_default="not_set",
        ))
        batch.add_column(sa.Column(
            "onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch.add_column(sa.Column(
            "memory_summary", sa.Text(), nullable=False, server_default="",
        ))
        batch.add_column(sa.Column(
            "memory_updated_at", sa.DateTime(), nullable=True,
        ))

    # habits: количественные привычки и цели
    with op.batch_alter_table("habits") as batch:
        batch.add_column(sa.Column("target_value", sa.Float(), nullable=True))
        batch.add_column(sa.Column("unit", sa.String(32), nullable=True))
        batch.add_column(sa.Column(
            "is_goal", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch.add_column(sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("habits") as batch:
        batch.drop_column("end_date")
        batch.drop_column("is_goal")
        batch.drop_column("unit")
        batch.drop_column("target_value")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("memory_updated_at")
        batch.drop_column("memory_summary")
        batch.drop_column("onboarding_completed")
        batch.drop_column("priority_focus")
        batch.drop_column("motivation_style")
