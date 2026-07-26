"""Search service (spec 16).

Executes a parsed intent over the canonical repositories and ranks results with
the evidence that matched. This is the correctness-first implementation; at scale
the same queries are served from the OpenSearch projection (spec 16.2), but the
result contract is identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .intent import QueryIntent, parse_query


@dataclass
class SearchResult:
    type: str                       # 'company' | 'person'
    id: int
    name: str | None
    domain: str | None
    score: float
    matched_on: list[str] = field(default_factory=list)
    evidence_ids: list[int] = field(default_factory=list)
    tier: str | None = None


class SearchService:
    def __init__(self, *, entities, signals, opportunities, edges, evidence):
        self._entities = entities
        self._signals = signals
        self._opps = opportunities
        self._edges = edges
        self._evidence = evidence

    def search(self, query: str, limit: int = 25) -> tuple[QueryIntent, list[SearchResult]]:
        intent = parse_query(query)
        if intent.target == "person":
            results = self._search_people(intent)
        else:
            results = self._search_companies(intent)
        results.sort(key=lambda r: r.score, reverse=True)
        return intent, results[:limit]

    # ------------------------------------------------------------------ companies
    def _search_companies(self, intent: QueryIntent) -> list[SearchResult]:
        out: list[SearchResult] = []
        for company in self._entities.all_of_type("company"):
            sigs = self._signals.for_company(company.id)
            matched: list[str] = []
            evidence_ids: list[int] = []

            if intent.hiring_department:
                hits = [s for s in sigs if s.signal_type == "hiring"
                        and (s.attributes.get("department") == intent.hiring_department)]
                if not hits:
                    continue
                matched.append(f"hiring:{intent.hiring_department}")
                evidence_ids += [e for s in hits for e in s.evidence_ids]

            if intent.tech:
                tech_hits = [s for s in sigs
                             if s.attributes.get("tech") == intent.tech
                             or s.intent_axis == intent.tech]
                stack = [t.lower() for t in (company.attributes.get("tech_stack") or [])]
                if not tech_hits and intent.tech not in stack:
                    continue
                matched.append(f"tech:{intent.tech}")
                evidence_ids += [e for s in tech_hits for e in s.evidence_ids]

            if intent.looking_for_axis:
                hits = [s for s in sigs if s.intent_axis == intent.looking_for_axis]
                if not hits:
                    continue
                matched.append(f"looking_for:{intent.looking_for_axis}")
                evidence_ids += [e for s in hits for e in s.evidence_ids]

            if intent.signal_type and not intent.hiring_department and not intent.looking_for_axis:
                hits = [s for s in sigs if s.signal_type == intent.signal_type]
                if not hits:
                    continue
                matched.append(f"signal:{intent.signal_type}")
                evidence_ids += [e for s in hits for e in s.evidence_ids]

            if intent.free_text:
                if not self._matches_text(company, sigs, intent.free_text):
                    continue
                matched.append(f"text:{intent.free_text}")

            if not matched:
                continue

            opps = [o for o in self._opps.list() if o.company_entity_id == company.id]
            best = max((o.opportunity_score for o in opps), default=0.0)
            tier = max(opps, key=lambda o: o.opportunity_score).tier if opps else None
            out.append(SearchResult(
                type="company", id=company.id,
                name=company.display_name or company.attributes.get("name"),
                domain=company.attributes.get("primary_domain"),
                score=round(best or 0.1, 4), matched_on=matched,
                evidence_ids=sorted(set(evidence_ids)), tier=tier,
            ))
        return out

    # ------------------------------------------------------------------ people
    def _search_people(self, intent: QueryIntent) -> list[SearchResult]:
        out: list[SearchResult] = []
        axis = intent.discussing_axis or intent.looking_for_axis
        for person in self._entities.all_of_type("person"):
            company_ids = [e.dst_entity_id for e in self._edges.out_edges(person.id, "works_at")]
            matched: list[str] = []
            evidence_ids: list[int] = []
            if axis:
                hit = False
                for cid in company_ids:
                    hits = [s for s in self._signals.for_company(cid) if s.intent_axis == axis]
                    if hits:
                        hit = True
                        evidence_ids += [e for s in hits for e in s.evidence_ids]
                if not hit:
                    continue
                matched.append(f"discussing:{axis}")
            elif intent.free_text:
                name = (person.display_name or "").lower()
                if intent.free_text not in name:
                    continue
                matched.append(f"text:{intent.free_text}")
            else:
                continue
            company = self._entities.get(company_ids[0]) if company_ids else None
            out.append(SearchResult(
                type="person", id=person.id,
                name=person.display_name or person.attributes.get("full_name"),
                domain=company.attributes.get("primary_domain") if company else None,
                score=0.5, matched_on=matched, evidence_ids=sorted(set(evidence_ids)),
            ))
        return out

    def _matches_text(self, company, sigs, text: str) -> bool:
        hay = (company.display_name or "").lower() + " " + (
            company.attributes.get("name") or ""
        ).lower()
        if text in hay:
            return True
        for s in sigs:
            for eid in s.evidence_ids:
                ev = self._evidence.get(eid)
                if ev and ev.snippet and text in ev.snippet.lower():
                    return True
        return False
