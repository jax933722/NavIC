from hypothesis import given
from hypothesis import strategies as st

from normalization import apex_domain, normalize_company_name, normalize_host


class TestCompanyName:
    def test_strips_legal_suffix(self):
        assert normalize_company_name("Acme Inc.") == "acme"
        assert normalize_company_name("Acme, LLC") == "acme"
        assert normalize_company_name("Acme Technologies Ltd") == "acme technologies"

    def test_collapses_and_lowercases(self):
        assert normalize_company_name("  ACME   Corp  ") == "acme"

    def test_keeps_single_token_even_if_suffix_like(self):
        # Never strip the only token.
        assert normalize_company_name("Co") == "co"

    def test_empty(self):
        assert normalize_company_name("") == ""
        assert normalize_company_name("   ") == ""

    def test_variants_converge(self):
        variants = ["Acme", "Acme Inc", "Acme, Inc.", "ACME  LLC"]
        assert len({normalize_company_name(v) for v in variants}) == 1

    @given(st.text())
    def test_idempotent(self, s):
        once = normalize_company_name(s)
        assert normalize_company_name(once) == once


class TestDomain:
    def test_apex_from_url(self):
        assert apex_domain("https://www.acme.com/team") == "acme.com"
        assert apex_domain("blog.acme.com") == "acme.com"
        assert apex_domain("acme.com") == "acme.com"

    def test_multi_label_suffix(self):
        assert apex_domain("https://www.acme.co.uk/careers") == "acme.co.uk"
        assert apex_domain("shop.acme.com.au") == "acme.com.au"

    def test_host_extraction(self):
        assert normalize_host("HTTPS://WWW.Acme.com/x") == "www.acme.com"
        assert normalize_host("acme.com") == "acme.com"

    def test_invalid(self):
        assert apex_domain("") == ""
        assert apex_domain("not a domain!!") == ""

    def test_ip_address_not_mangled(self):
        # IPs are not registrable domains — must not be sliced to "0.1".
        assert apex_domain("http://127.0.0.1:9999/") == "127.0.0.1"
        assert apex_domain("http://192.168.1.10/x") == "192.168.1.10"

    @given(st.text())
    def test_apex_idempotent(self, s):
        once = apex_domain(s)
        # apex of an apex is itself (when it produced a valid apex)
        if once:
            assert apex_domain(once) == once
