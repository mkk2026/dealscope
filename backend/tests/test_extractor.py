from app.pipeline.extractor import _coerce_facts


def test_parses_facts_object():
    raw = '{"facts":[{"claim":"Free tier $0","category":"overview","confidence":0.9}]}'
    facts = _coerce_facts(raw, "https://x/pricing")
    assert len(facts) == 1
    assert facts[0].claim == "Free tier $0"
    assert facts[0].category == "overview"
    assert facts[0].source_url == "https://x/pricing"  # attached by us, not the model


def test_bad_category_defaults_overview():
    raw = '{"facts":[{"claim":"x","category":"BOGUS","confidence":0.5}]}'
    assert _coerce_facts(raw, "u")[0].category == "overview"


def test_bad_confidence_defaults_half():
    raw = '{"facts":[{"claim":"x","category":"hiring","confidence":"high"}]}'
    assert _coerce_facts(raw, "u")[0].confidence == 0.5


def test_skips_items_without_claim():
    raw = '{"facts":[{"category":"hiring"},{"claim":"keep","category":"hiring","confidence":0.7}]}'
    facts = _coerce_facts(raw, "u")
    assert [f.claim for f in facts] == ["keep"]


def test_junk_returns_empty():
    assert _coerce_facts("not json", "u") == []
    assert _coerce_facts('{"nope": 1}', "u") == []
