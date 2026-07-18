"""Signal taxonomy: types, default strengths, department/intent maps (spec 05 §2)."""

from __future__ import annotations

from enum import StrEnum


class SignalType(StrEnum):
    FUNDING_RAISED = "funding_raised"
    HIRING = "hiring"
    TECH_ADOPTION = "tech_adoption"
    TECH_CHURN = "tech_churn"
    PRODUCT_LAUNCH = "product_launch"
    PAIN_MENTION = "pain_mention"
    LEADERSHIP_CHANGE = "leadership_change"
    EXPANSION = "expansion"


SIGNAL_DEFAULT_STRENGTH: dict[str, float] = {
    SignalType.FUNDING_RAISED: 0.7,
    SignalType.HIRING: 0.5,
    SignalType.TECH_ADOPTION: 0.6,
    SignalType.TECH_CHURN: 0.8,
    SignalType.PRODUCT_LAUNCH: 0.5,
    SignalType.PAIN_MENTION: 0.7,
    SignalType.LEADERSHIP_CHANGE: 0.6,
    SignalType.EXPANSION: 0.5,
}

# Role keyword -> department (drives Silver decision-maker inference, spec 05 §5.1).
DEPARTMENT_BY_ROLE: dict[str, str] = {
    "sdr": "Sales",
    "sales": "Sales",
    "account executive": "Sales",
    "revops": "RevOps",
    "revenue operations": "RevOps",
    "growth": "Marketing",
    "marketing": "Marketing",
    "demand gen": "Marketing",
    "email": "Marketing",
    "engineer": "Engineering",
    "developer": "Engineering",
    "devops": "Engineering",
    "data": "Data",
    "analytics": "Data",
    "customer success": "Customer Success",
    "support": "Customer Success",
}

# Department -> suggested decision-maker roles (Silver).
DECISION_MAKER_BY_DEPARTMENT: dict[str, list[str]] = {
    "Sales": ["VP Sales", "Head of Sales", "Head of RevOps"],
    "RevOps": ["Head of RevOps", "VP Sales Ops"],
    "Marketing": ["VP Marketing", "Head of Growth", "Head of Demand Gen"],
    "Engineering": ["VP Engineering", "CTO", "Head of Platform"],
    "Data": ["Head of Data", "VP Analytics"],
    "Customer Success": ["VP Customer Success", "Head of Support"],
}

# Intent axes for pain mentions -> the tool category the company may be in-market for.
PAIN_AXES: dict[str, tuple[str, ...]] = {
    "crm": ("crm", "salesforce alternative", "hubspot alternative", "pipedrive"),
    "deliverability": ("deliverability", "bounce rate", "spam folder", "email deliverability"),
    "analytics": ("analytics", "dashboards", "reporting", "bi tool"),
    "data_enrichment": ("data enrichment", "lead enrichment", "contact data"),
    "outbound": ("outbound", "cold email", "sales engagement", "sequencing"),
}
