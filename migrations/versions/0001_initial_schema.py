"""Initial schema — core entity/evidence/graph/opportunity tables.

For this greenfield baseline the migration creates the full ORM metadata in one
step (``Base.metadata.create_all``), keeping ``storage.models`` the single source
of truth and avoiding drift. Subsequent migrations use granular ``op`` operations.

Deferred to follow-up hand-written migrations (not expressible in ORM metadata):
  - monthly RANGE partitioning of evidence/raw_document/timeline_event/score_history
  - Apache AGE graph bootstrap + pgvector / pg_trgm indexes
(see docs/schema/schema.sql and spec 01 §6).

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

from storage import Base
from storage import models  # noqa: F401  (register tables on Base.metadata)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
