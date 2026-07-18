"""Collector registry (spec 03 §6.1).

Collectors self-register via ``@register``. The runtime/scheduler looks them up
by slug. Adding a source never edits core — it adds a module and a registration.
"""

from __future__ import annotations

from .base import BaseCollector

REGISTRY: dict[str, type[BaseCollector]] = {}


def register(cls: type[BaseCollector]) -> type[BaseCollector]:
    slug = getattr(cls, "collector_slug", None)
    if not slug:
        raise ValueError(f"{cls.__name__} must define collector_slug")
    REGISTRY[slug] = cls
    return cls


def get_collector(slug: str) -> BaseCollector:
    if slug not in REGISTRY:
        raise KeyError(f"unknown collector: {slug}")
    return REGISTRY[slug]()
