"""Pairwise matching (spec 04 §5).

Computes a feature vector for a (candidate, existing) pair, then a match
probability via a transparent weighted-logistic scorer (v1). Hard rules
(domain-exact for companies, email/handle-exact for people) short-circuit to a
decisive match. The interface ``score_pair`` is model-agnostic so a trained
classifier can replace the weights in v2 (spec 04 §5.3) with no caller change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from normalization import (
    apex_domain,
    name_soundex,
    normalize_company_name,
    normalize_person_name,
)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _jaro_winkler(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_dist = max(len(s1), len(s2)) // 2 - 1
    match = 0
    s1_flags = [False] * len(s1)
    s2_flags = [False] * len(s2)
    for i, c1 in enumerate(s1):
        lo = max(0, i - max_dist)
        hi = min(i + max_dist + 1, len(s2))
        for j in range(lo, hi):
            if not s2_flags[j] and s2[j] == c1:
                s1_flags[i] = s2_flags[j] = True
                match += 1
                break
    if match == 0:
        return 0.0
    t = 0
    k = 0
    for i in range(len(s1)):
        if s1_flags[i]:
            while not s2_flags[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t /= 2
    jaro = (match / len(s1) + match / len(s2) + (match - t) / match) / 3
    prefix = 0
    for c1, c2 in zip(s1, s2, strict=False):
        if c1 == c2:
            prefix += 1
        else:
            break
        if prefix == 4:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


# Weights tuned so that name-only agreement (identical names, but NO shared
# domain or handle) lands in the REVIEW band (~0.83), never auto-merge — two
# firms can share a name. Domain-exact is a hard rule (=1.0); a shared handle
# still pushes into auto-merge. Biasing toward under-merge is deliberate (spec
# 04 P2 / risk R1): a duplicate is fixable, a wrong merge corrupts.
COMPANY_WEIGHTS = {
    "bias": -4.8,
    "domain_exact": 8.0,
    "name_jw": 3.2,
    "name_token_jaccard": 2.0,
    "name_soundex_match": 1.2,
    "handle_match": 4.0,
    "geo_match": 0.8,
}


@dataclass(frozen=True)
class CompanyFeatures:
    domain_exact: float
    name_jw: float
    name_token_jaccard: float
    name_soundex_match: float
    handle_match: float
    geo_match: float


def company_features(a: dict, b: dict) -> CompanyFeatures:
    ad = a.get("primary_domain") or apex_domain(a.get("url", "") or "")
    bd = b.get("primary_domain") or apex_domain(b.get("url", "") or "")
    an = normalize_company_name(a.get("name") or a.get("display_name") or "")
    bn = normalize_company_name(b.get("name") or b.get("display_name") or "")
    handles_a = {a.get(f) for f in ("linkedin_slug", "github_org", "twitter") if a.get(f)}
    handles_b = {b.get(f) for f in ("linkedin_slug", "github_org", "twitter") if b.get(f)}
    return CompanyFeatures(
        domain_exact=1.0 if ad and ad == bd else 0.0,
        name_jw=_jaro_winkler(an, bn),
        name_token_jaccard=_jaccard(set(an.split()), set(bn.split())),
        name_soundex_match=1.0 if an and name_soundex(an) == name_soundex(bn) else 0.0,
        handle_match=1.0 if handles_a & handles_b else 0.0,
        geo_match=1.0 if a.get("hq_country") and a.get("hq_country") == b.get("hq_country")
        else 0.0,
    )


# ------------------------------------------------------------------ people
PERSON_WEIGHTS = {
    "bias": -5.0,
    "email_exact": 10.0,
    "handle_match": 8.0,
    "name_jw": 1.5,                 # name alone is weak (context-first, spec 04 P5)
    "same_company": 3.5,
    "role_similarity": 1.0,
    "doc_cooccurrence": 1.5,
}


@dataclass(frozen=True)
class PersonFeatures:
    email_exact: float
    handle_match: float
    name_jw: float
    same_company: float
    role_similarity: float
    doc_cooccurrence: float


def person_features(a: dict, b: dict) -> PersonFeatures:
    an = normalize_person_name(a.get("full_name") or a.get("name") or "")
    bn = normalize_person_name(b.get("full_name") or b.get("name") or "")
    handles_a = {a.get(f) for f in ("github_handle", "twitter", "linkedin_slug") if a.get(f)}
    handles_b = {b.get(f) for f in ("github_handle", "twitter", "linkedin_slug") if b.get(f)}
    ca = a.get("company_domain") or a.get("company_apex")
    cb = b.get("company_domain") or b.get("company_apex")
    ra = normalize_company_name(a.get("current_role") or "")
    rb = normalize_company_name(b.get("current_role") or "")
    return PersonFeatures(
        email_exact=1.0 if a.get("email") and a.get("email") == b.get("email") else 0.0,
        handle_match=1.0 if handles_a & handles_b else 0.0,
        name_jw=_jaro_winkler(an, bn),
        same_company=1.0 if ca and ca == cb else 0.0,
        role_similarity=_jaccard(set(ra.split()), set(rb.split())),
        doc_cooccurrence=1.0 if a.get("doc_id") and a.get("doc_id") == b.get("doc_id") else 0.0,
    )


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def score_company_pair(a: dict, b: dict) -> float:
    f = company_features(a, b)
    if f.domain_exact:  # hard rule (spec 04 §5.4)
        return 1.0
    w = COMPANY_WEIGHTS
    z = (
        w["bias"]
        + w["name_jw"] * f.name_jw
        + w["name_token_jaccard"] * f.name_token_jaccard
        + w["name_soundex_match"] * f.name_soundex_match
        + w["handle_match"] * f.handle_match
        + w["geo_match"] * f.geo_match
    )
    return _sigmoid(z)


def score_person_pair(a: dict, b: dict) -> float:
    f = person_features(a, b)
    if f.email_exact or f.handle_match:  # hard rules
        return 1.0
    w = PERSON_WEIGHTS
    z = (
        w["bias"]
        + w["name_jw"] * f.name_jw
        + w["same_company"] * f.same_company
        + w["role_similarity"] * f.role_similarity
        + w["doc_cooccurrence"] * f.doc_cooccurrence
    )
    return _sigmoid(z)
