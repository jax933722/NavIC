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
    # Someone publicly asking for a vendor/service recommendation — the most
    # explicit buying signal there is ("can anyone recommend a ... for ...").
    SOLICITATION = "solicitation"


SIGNAL_DEFAULT_STRENGTH: dict[str, float] = {
    SignalType.FUNDING_RAISED: 0.7,
    SignalType.HIRING: 0.5,
    SignalType.TECH_ADOPTION: 0.6,
    SignalType.TECH_CHURN: 0.8,
    SignalType.PRODUCT_LAUNCH: 0.5,
    SignalType.PAIN_MENTION: 0.7,
    SignalType.LEADERSHIP_CHANGE: 0.6,
    SignalType.EXPANSION: 0.5,
    # Explicit in-market request — the strongest deterministic signal we detect.
    SignalType.SOLICITATION: 0.9,
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

# Service categories a solicitation may be for -> phrases that identify them.
# The category becomes the opportunity's intent axis (what they want to buy).
# Order matters: the first category with a matching phrase wins, so more-specific
# categories (security, mobile) precede the broad web/dev ones.
SERVICE_AXES: dict[str, tuple[str, ...]] = {
    "security": ("malware", "hacked", "penetration test", "pentest", "vulnerability",
                 "security audit", "cybersecurity", "security expert", "incident response",
                 "malware removal"),
    "mobile_app": ("flutter", "react native", "ios app", "android app", "mobile app",
                   "mobile developer", "mobile application", "app developer",
                   "app development", "swift", "kotlin"),
    "web_development": ("web developer", "website development", "e-commerce website",
                        "ecommerce website", "full stack", "full-stack", "fullstack",
                        "mern", "mean", "backend", "back-end", "node.js", "django",
                        "laravel", "rails"),
    "web_design": ("website design", "web design", "website designer", "web designer",
                   "landing page", "product page", "shopify", "webflow", "wordpress",
                   "ui/ux", "ux designer", "redesign"),
    "seo": ("seo", "search engine optimization", "organic traffic", "backlinks"),
    "paid_ads": ("google ads", "paid ads", "ppc", "paid media", "facebook ads",
                 "meta ads", "performance marketing"),
    "branding": ("branding", "brand identity", "logo design", "rebrand"),
    "content": ("copywriter", "copywriting", "content writer", "blog writer",
                "content marketing"),
    "video": ("video editor", "video production", "explainer video", "motion graphics"),
    "development": ("developer", "software agency", "dev agency", "custom software",
                    "programmer", "engineer"),
    "crm": ("crm", "hubspot", "salesforce", "pipedrive"),
    "email_marketing": ("email marketing", "klaviyo", "mailchimp", "newsletter"),
}

# Service category -> the department that typically owns that purchase (drives the
# Silver decision-maker suggestion when no specific person is resolved).
SERVICE_DEPARTMENT: dict[str, str] = {
    "security": "Engineering",
    "mobile_app": "Engineering",
    "web_development": "Engineering",
    "development": "Engineering",
    "web_design": "Marketing",
    "seo": "Marketing",
    "paid_ads": "Marketing",
    "branding": "Marketing",
    "content": "Marketing",
    "video": "Marketing",
    "email_marketing": "Marketing",
    "crm": "Sales",
}

# Known tech tokens to lift from a solicitation (what they want built with).
SOLICITATION_STACK: tuple[str, ...] = (
    "flutter", "react native", "react", "node.js", "node", "express", "mongodb",
    "mern", "mean", "vue", "angular", "next.js", "django", "rails", "laravel",
    "php", "swift", "kotlin", "ios", "android", "wordpress", "shopify", "webflow",
)
