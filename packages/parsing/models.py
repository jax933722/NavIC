"""Parsed-document model — the Parsed medallion layer (blueprint §14.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedLink(BaseModel):
    href: str
    text: str = ""
    rel: str | None = None


class ParsedDocument(BaseModel):
    url: str
    title: str | None = None
    text: str = ""
    links: list[ParsedLink] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    # Structured extras (JSON-LD, og: tags) surfaced for deterministic extraction.
    structured: dict = Field(default_factory=dict)

    def internal_paths(self, keywords: tuple[str, ...]) -> list[str]:
        """Return same-site links whose href/text hint at a keyword (seed expansion)."""
        out: list[str] = []
        for link in self.links:
            hay = f"{link.href} {link.text}".lower()
            if any(k in hay for k in keywords):
                out.append(link.href)
        return out
