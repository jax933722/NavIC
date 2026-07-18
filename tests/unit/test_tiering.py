from opportunities import OpportunityPresence, Tier, classify


def test_gold_requires_full_relationship():
    p = OpportunityPresence(
        company=True,
        domain=True,
        person=True,
        role=True,
        relationship_evidence=True,
        buying_signal=True,
    )
    assert classify(p) == Tier.GOLD


def test_missing_relationship_evidence_is_not_gold():
    p = OpportunityPresence(
        company=True,
        domain=True,
        person=True,
        role=True,
        relationship_evidence=False,  # the exact Silver/Gold line
        buying_signal=True,
        suggested_department=True,
        suggested_role=True,
    )
    assert classify(p) == Tier.SILVER


def test_silver():
    p = OpportunityPresence(
        company=True,
        domain=True,
        buying_signal=True,
        suggested_department=True,
        suggested_role=True,
    )
    assert classify(p) == Tier.SILVER


def test_bronze_weak_signal():
    p = OpportunityPresence(company=True, domain=True, weak_signal=True)
    assert classify(p) == Tier.BRONZE


def test_unqualified_without_domain():
    p = OpportunityPresence(company=True, weak_signal=True)
    assert classify(p) == Tier.UNQUALIFIED


def test_tier_ordering_is_stable_under_field_order():
    # Presence is a frozen dataclass; construction order must not matter.
    a = OpportunityPresence(domain=True, company=True, weak_signal=True)
    b = OpportunityPresence(company=True, weak_signal=True, domain=True)
    assert classify(a) == classify(b) == Tier.BRONZE
