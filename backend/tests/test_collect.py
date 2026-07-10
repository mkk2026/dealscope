# Regression: ISSUE-005 — a schemeless URL ("stripe.com") collected 0 sources and
# produced a fake "Pass — 0/100" verdict instead of screening the company.
# Found by /qa on 2026-07-10 against the deployed HF Space.
# Report: .gstack/qa-reports/qa-report-dealscope-2026-07-10.md

from app.pipeline.collect import normalize_url


def test_normalize_url_adds_missing_scheme():
    assert normalize_url("stripe.com") == "https://stripe.com"
    assert normalize_url("  stripe.com  ") == "https://stripe.com"


def test_normalize_url_keeps_explicit_scheme():
    assert normalize_url("https://stripe.com") == "https://stripe.com"
    assert normalize_url("http://stripe.com") == "http://stripe.com"
    assert normalize_url("HTTPS://stripe.com") == "HTTPS://stripe.com"


def test_normalize_url_empty_stays_empty():
    assert normalize_url("") == ""
    assert normalize_url("   ") == ""
