"""Daily digest (spec 07 §8 / blueprint §18).

Summarises what changed since a cutoff: newly-created opportunities and
tier upgrades (from the promotion ledger). This is the operator's "what's new /
what got better today" brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

_TIER_RANK = {"bronze": 1, "silver": 2, "gold": 3, "unqualified": 0}


@dataclass
class DigestItem:
    opportunity_id: int
    company_name: str | None
    domain: str | None
    tier: str
    thesis: str | None
    kind: str            # 'new' | 'upgraded'
    detail: str
    score: float


@dataclass
class Digest:
    generated_at: datetime
    since: datetime
    new: list[DigestItem] = field(default_factory=list)
    upgraded: list[DigestItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new) + len(self.upgraded)


def build_digest(*, opportunities, transitions, entities, since: datetime | None = None,
                 now: datetime | None = None) -> Digest:
    now = now or datetime.now(UTC)
    since = since or (now - timedelta(days=1))
    digest = Digest(generated_at=now, since=since)

    opps_by_id = {o.id: o for o in opportunities.list()}

    def company_name(company_id):
        ent = entities.get(company_id)
        return (ent.display_name or ent.attributes.get("name"), ent.attributes.get("primary_domain")) \
            if ent else (None, None)

    for opp in opps_by_id.values():
        if opp.created_at >= since:
            name, domain = company_name(opp.company_entity_id)
            digest.new.append(DigestItem(
                opportunity_id=opp.id, company_name=name, domain=domain, tier=opp.tier,
                thesis=opp.thesis, kind="new", detail=f"new {opp.tier}", score=opp.opportunity_score,
            ))

    # Upgrades from the promotion ledger.
    seen_upgrade: set[int] = set()
    for opp_id, opp in opps_by_id.items():
        trans = transitions.for_opportunity(opp_id)
        upgrades = [
            t for t in trans
            if t.created_at >= since
            and _TIER_RANK.get(t.to_tier, 0) > _TIER_RANK.get(t.from_tier or "unqualified", 0)
        ]
        if upgrades and opp_id not in seen_upgrade:
            seen_upgrade.add(opp_id)
            latest = upgrades[-1]
            name, domain = company_name(opp.company_entity_id)
            digest.upgraded.append(DigestItem(
                opportunity_id=opp_id, company_name=name, domain=domain, tier=opp.tier,
                thesis=opp.thesis, kind="upgraded",
                detail=f"{latest.from_tier or 'new'} → {latest.to_tier}",
                score=opp.opportunity_score,
            ))

    digest.new.sort(key=lambda i: i.score, reverse=True)
    digest.upgraded.sort(key=lambda i: i.score, reverse=True)
    return digest
