"""Labeled company match/no-match pairs for the ER evaluation gate (spec 09 §3.3).

Grown from the operator review queue over time. `label` True = same company.
The over-merge canary pairs (similar names, distinct companies) are labeled False
and must never be predicted as matches.
"""

PAIRS: list[tuple[dict, dict, bool]] = [
    # --- true matches (same company, different observations) ---
    ({"name": "Acme Inc", "primary_domain": "acme.com"},
     {"name": "Acme, LLC", "primary_domain": "acme.com"}, True),
    ({"name": "HubSpot", "primary_domain": "hubspot.com"},
     {"name": "HubSpot, Inc.", "primary_domain": "hubspot.com"}, True),
    ({"name": "Stripe", "primary_domain": "stripe.com", "hq_country": "US"},
     {"name": "Stripe Payments", "primary_domain": "stripe.com", "hq_country": "US"}, True),
    ({"name": "Globex Corporation", "primary_domain": "globex.io"},
     {"name": "Globex Corp", "primary_domain": "globex.io"}, True),
    ({"name": "Northwind Traders", "primary_domain": "northwind.com",
      "linkedin_slug": "northwind"},
     {"name": "Northwind", "primary_domain": "nw-different.com", "linkedin_slug": "northwind"},
     True),  # same LinkedIn handle
    ({"name": "Contoso Ltd", "primary_domain": "contoso.co.uk"},
     {"name": "Contoso Limited", "primary_domain": "contoso.co.uk"}, True),
    ({"name": "Initech", "primary_domain": "initech.com"},
     {"name": "Initech Software", "primary_domain": "initech.com"}, True),

    # --- true non-matches (distinct companies) ---
    ({"name": "Acme Corp", "primary_domain": "acme.com"},
     {"name": "Globex Software", "primary_domain": "globex.com"}, False),
    ({"name": "Stripe", "primary_domain": "stripe.com"},
     {"name": "Square", "primary_domain": "squareup.com"}, False),
    ({"name": "HubSpot", "primary_domain": "hubspot.com"},
     {"name": "Salesforce", "primary_domain": "salesforce.com"}, False),

    # --- over-merge canaries (similar names, DIFFERENT companies) ---
    ({"name": "Acme Software", "primary_domain": "acme-sw.com", "hq_country": "US"},
     {"name": "Acme Logistics", "primary_domain": "acmelog.com", "hq_country": "DE"}, False),
    ({"name": "Apex Systems", "primary_domain": "apexsystems.com"},
     {"name": "Apex Legal", "primary_domain": "apexlegal.co"}, False),
    ({"name": "Summit Partners", "primary_domain": "summitpartners.com"},
     {"name": "Summit Roofing", "primary_domain": "summitroof.com"}, False),
]
