from app.pipeline.github import extract_github_org


def test_prefers_domain_match_over_first_link():
    html = 'footer: github.com/somedependency and github.com/linear here'
    assert extract_github_org(html, domain_hint="linear.app") == "linear"


def test_falls_back_to_first_non_skip():
    html = 'github.com/acmecorp social links'
    assert extract_github_org(html) == "acmecorp"


def test_skips_known_non_org_paths():
    html = 'github.com/features github.com/pricing github.com/realorg'
    assert extract_github_org(html) == "realorg"


def test_none_when_no_github():
    assert extract_github_org("no links at all") is None
