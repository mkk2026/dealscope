"""Network-gated golden-company harness.

Runs the real collector (no LLM) against known companies and checks we found the
right entity and enough sources. This is the demo safety net: run it before the
demo to confirm your stage companies still screen clean.

    pytest -m integration tests/test_golden.py
"""

import json
from pathlib import Path

import pytest

from app.pipeline.collect import collect
from app.pipeline.models import SourceKind

GOLDEN = json.loads((Path(__file__).parent / "golden_companies.json").read_text())


@pytest.mark.integration
@pytest.mark.parametrize("case", GOLDEN, ids=[c["domain"] for c in GOLDEN])
async def test_golden_company_collects(case):
    docs = await collect(case["url"])
    assert len(docs) >= case["expect_min_sources"], f"too few sources for {case['url']}"
    assert any(d.kind == SourceKind.WEBPAGE for d in docs)

    # collect() resolves the GitHub entity from raw HTML and emits a GITHUB source.
    # Check that real pipeline output, not the cleaned text (which has no hrefs).
    if case.get("expect_github_org"):
        github_docs = [d for d in docs if d.kind == SourceKind.GITHUB]
        assert github_docs, f"no GitHub source discovered for {case['url']}"
        org = github_docs[0].meta.get("org")
        assert org and org.lower() == case["expect_github_org"].lower(), \
            f"got org={org!r}, expected {case['expect_github_org']!r}"
