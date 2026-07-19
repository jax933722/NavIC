"""maintenance — scheduled housekeeping (spec 01 §6, blueprint §18).

Monthly partition pre-creation for the time-partitioned giants
(evidence/raw_document/timeline_event/score_history) and retention tiering. The
partition helpers are pure and testable; a maintenance worker runs them on a tick.
"""

from .partitions import (
    create_partition_sql,
    monthly_partition_bounds,
    next_partitions,
    partition_name,
)

__all__ = [
    "monthly_partition_bounds",
    "partition_name",
    "create_partition_sql",
    "next_partitions",
]
