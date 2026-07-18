"""Initial schema — full baseline.

Greenfield baseline: creates the entire current ORM schema in one revision from
``storage.models`` (the single source of truth). This is the standard "squash to
baseline" for a pre-release project with no deployed database.

Rule going forward: this is the ONLY migration that uses ``Base.metadata`` —
every subsequent migration uses explicit ``op.*`` operations, so incremental
changes never collide with the metadata's latest shape.

Deferred to follow-up migrations (not expressible in ORM metadata):
  - monthly RANGE partitioning of evidence/raw_document/timeline_event
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
