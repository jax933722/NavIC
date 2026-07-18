from entities import score_company_pair, score_person_pair
from entities.blocking import company_blocking_keys, person_blocking_keys


class TestCompanyMatcher:
    def test_domain_exact_is_decisive(self):
        a = {"name": "Acme", "primary_domain": "acme.com"}
        b = {"name": "Totally Different", "primary_domain": "acme.com"}
        assert score_company_pair(a, b) == 1.0

    def test_same_name_variants_match_high(self):
        a = {"name": "Acme Inc", "primary_domain": "acme.com"}
        b = {"name": "Acme, LLC", "primary_domain": "acme.io"}  # diff domain, same name
        assert score_company_pair(a, b) > 0.6

    def test_distinct_companies_do_not_match(self):
        a = {"name": "Acme Corp", "primary_domain": "acme.com"}
        b = {"name": "Globex Software", "primary_domain": "globex.com"}
        assert score_company_pair(a, b) < 0.4

    def test_over_merge_canary_similar_names_diff_domain_diff_geo(self):
        # "Acme Software" vs "Acme Logistics" — same first token, must NOT auto-merge.
        a = {"name": "Acme Software", "primary_domain": "acme-sw.com", "hq_country": "US"}
        b = {"name": "Acme Logistics", "primary_domain": "acmelog.com", "hq_country": "DE"}
        assert score_company_pair(a, b) < 0.90


class TestPersonMatcher:
    def test_email_exact_is_decisive(self):
        a = {"full_name": "J. Roe", "email": "jane@acme.com"}
        b = {"full_name": "Jane Roe", "email": "jane@acme.com"}
        assert score_person_pair(a, b) == 1.0

    def test_handle_match_is_decisive(self):
        a = {"full_name": "Jane Roe", "github_handle": "jroe"}
        b = {"full_name": "J Roe", "github_handle": "jroe"}
        assert score_person_pair(a, b) == 1.0

    def test_same_name_different_company_is_not_a_match(self):
        # The classic over-merge trap: common name, no shared context.
        a = {"full_name": "John Smith", "company_domain": "acme.com"}
        b = {"full_name": "John Smith", "company_domain": "globex.com"}
        assert score_person_pair(a, b) < 0.90

    def test_same_name_same_company_raises_confidence(self):
        a = {"full_name": "John Smith", "company_domain": "acme.com", "current_role": "VP Sales"}
        b = {"full_name": "John Smith", "company_domain": "acme.com", "current_role": "VP of Sales"}
        low = score_person_pair(
            {"full_name": "John Smith", "company_domain": "acme.com"},
            {"full_name": "John Smith", "company_domain": "globex.com"},
        )
        assert score_person_pair(a, b) > low


class TestBlocking:
    def test_company_keys_include_apex_and_name(self):
        keys = company_blocking_keys({"name": "Acme Inc", "primary_domain": "acme.com"})
        types = {k.key_type for k in keys}
        assert "apex_domain" in types and "name_core" in types

    def test_person_context_key(self):
        keys = person_blocking_keys({"full_name": "Jane Roe", "company_domain": "acme.com"})
        assert any(k.key_type == "name_company" for k in keys)
