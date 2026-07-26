"""Blocking-key generation (spec 04 §4).

Blocking generates cheap recall keys so we only score pairs within shared
blocks — never all-pairs (O(n^2) is fatal at 100M). A candidate lands in
several blocks; the union is deduped by pairwise scoring.
"""

from __future__ import annotations

from dataclasses import dataclass

from normalization import (
    apex_domain,
    name_soundex,
    normalize_company_name,
    normalize_person_name,
)


@dataclass(frozen=True)
class BlockingKey:
    key_type: str
    key_value: str


def company_blocking_keys(attributes: dict) -> list[BlockingKey]:
    keys: list[BlockingKey] = []
    apex = attributes.get("primary_domain") or apex_domain(attributes.get("url", "") or "")
    if apex:
        keys.append(BlockingKey("apex_domain", apex))
    name = attributes.get("name") or attributes.get("display_name")
    if name:
        core = normalize_company_name(name)
        if core:
            keys.append(BlockingKey("name_core", core))
            keys.append(BlockingKey("name_soundex", name_soundex(core)))
    for handle_field in ("linkedin_slug", "github_org", "twitter"):
        val = attributes.get(handle_field)
        if val:
            keys.append(BlockingKey(f"handle_{handle_field}", str(val).lower()))
    return _dedupe(keys)


def person_blocking_keys(attributes: dict) -> list[BlockingKey]:
    keys: list[BlockingKey] = []
    email = attributes.get("email")
    if email:
        keys.append(BlockingKey("email", str(email).strip().lower()))
    name = attributes.get("full_name") or attributes.get("name")
    norm = normalize_person_name(name) if name else ""
    company_apex = attributes.get("company_domain") or attributes.get("company_apex")
    for handle_field in ("github_handle", "twitter", "linkedin_slug"):
        val = attributes.get(handle_field)
        if val:
            keys.append(BlockingKey(f"handle_{handle_field}", str(val).lower()))
            if norm:
                keys.append(BlockingKey("name_handle", f"{norm}|{str(val).lower()}"))
    if norm and company_apex:
        # Context-first: name is only a useful block when paired with a company.
        keys.append(BlockingKey("name_company", f"{norm}|{company_apex}"))
    if norm:
        keys.append(BlockingKey("name_soundex", name_soundex(norm)))
    return _dedupe(keys)


def _dedupe(keys: list[BlockingKey]) -> list[BlockingKey]:
    seen: set[tuple[str, str]] = set()
    out: list[BlockingKey] = []
    for k in keys:
        if not k.key_value:
            continue
        tup = (k.key_type, k.key_value)
        if tup not in seen:
            seen.add(tup)
            out.append(k)
    return out
