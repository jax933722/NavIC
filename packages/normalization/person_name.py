"""Person name normalization + soundex (spec 04 §3.3).

Person matching is context-first (company/handle beat name), so name
normalization exists mainly to build blocking keys, not to drive matches alone.
"""

from __future__ import annotations

import re
import unicodedata

_HONORIFICS = frozenset({"mr", "mrs", "ms", "dr", "prof", "sir", "mx"})
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "phd", "md"})
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_person_name(raw: str) -> str:
    """Lowercase, de-accent, drop honorifics/suffixes, collapse whitespace."""
    if not raw:
        return ""
    text = _strip_accents(raw).lower()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    if not text:
        return ""
    tokens = [t for t in text.split(" ") if t not in _HONORIFICS]
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def soundex(token: str) -> str:
    """Classic Soundex code for a single token (blocking key helper)."""
    token = _strip_accents(token).upper()
    token = re.sub(r"[^A-Z]", "", token)
    if not token:
        return ""
    codes = {
        **dict.fromkeys("BFPV", "1"),
        **dict.fromkeys("CGJKQSXZ", "2"),
        **dict.fromkeys("DT", "3"),
        "L": "4",
        **dict.fromkeys("MN", "5"),
        "R": "6",
    }
    first = token[0]
    encoded = first
    prev = codes.get(first, "")
    for ch in token[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            encoded += code
        if ch not in "HW":
            prev = code
    encoded = (encoded + "000")[:4]
    return encoded


def name_soundex(name: str) -> str:
    """Soundex over the full normalized name (joined token codes)."""
    norm = normalize_person_name(name) or name.lower()
    parts = [soundex(t) for t in norm.split(" ") if t]
    return "-".join(p for p in parts if p)
