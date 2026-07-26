"""Declarative base + shared column types."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def created_at_column():
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
