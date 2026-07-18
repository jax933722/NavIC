"""Add timeline_event (per-company chronology, spec 05 §2 / M2).

First incremental migration after the baseline — uses explicit op.* only.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timeline_event",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("company_entity_id", sa.BigInteger, sa.ForeignKey("entity.id"), nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("signal_id", sa.BigInteger, sa.ForeignKey("signal.id"), nullable=True),
        sa.Column("evidence_ids", ARRAY(sa.BigInteger), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "timeline_company_idx", "timeline_event", ["company_entity_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("timeline_company_idx", table_name="timeline_event")
    op.drop_table("timeline_event")
