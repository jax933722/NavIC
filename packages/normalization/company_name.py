"""Company name normalization (spec 04 §3.1).

Lowercase, strip punctuation, collapse whitespace, remove legal suffixes.
Deterministic and idempotent: ``normalize(normalize(x)) == normalize(x)``.
"""

from __future__ import annotations

import re

# Legal suffixes stripped to a canonical name core (spec 04 §3.1).
LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "l.l.c",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
        "sa",
        "s.a",
        "plc",
        "pvt",
        "pte",
        "bv",
        "b.v",
        "ag",
        "oy",
        "ab",
        "srl",
        "sas",
        "kg",
        "nv",
        "n.v",
    }
)

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_company_name(raw: str) -> str:
    """Return the canonical name core (suffix-stripped, lowercased)."""
    if not raw:
        return ""
    text = raw.strip().lower()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    if not text:
        return ""
    tokens = text.split(" ")
    # Drop trailing legal suffix tokens (e.g. "acme inc" -> "acme").
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)
