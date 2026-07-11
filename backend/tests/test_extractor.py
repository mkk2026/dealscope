import httpx
import openai

from app.llm.client import Completion
from app.pipeline import extractor
from app.pipeline.extractor import _coerce_facts, extract_facts
from app.pipeline.models import SourceDocument, SourceKind


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


# Regression: a fully rate-limited extraction stage silently returned 0 facts,
# and the screen degraded to a misleading "Pass — 0/100" instead of an error.
# Found by /qa live verification on 2026-07-11 against the deployed HF Space.

def _rate_limit_error() -> openai.RateLimitError:
    req = httpx.Request("POST", "https://api.fireworks.ai/inference/v1/chat/completions")
    return openai.RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)


def _doc(url="https://x/pricing"):
    return SourceDocument(url=url, kind=SourceKind.WEBPAGE, title="t", text="text")


_ONE_FACT = '{"facts":[{"claim":"Free tier $0","category":"overview","confidence":0.9}]}'


class _PerUrlClient:
    """fail_urls raise RateLimitError on every attempt; others return one fact."""

    def __init__(self, fail_urls=()):
        self.fail_urls = set(fail_urls)
        self.calls = 0

    async def complete(self, **kwargs) -> Completion:
        self.calls += 1
        url = kwargs["user"].split("PAGE URL: ")[1].split("\n")[0]
        if url in self.fail_urls:
            raise _rate_limit_error()
        return Completion(text=_ONE_FACT, prompt_tokens=5, completion_tokens=5)


async def test_all_pages_throttled_raises_instead_of_fake_pass(monkeypatch):
    monkeypatch.setattr(extractor, "_RATE_LIMIT_RETRY_DELAY_S", 0)
    docs = [_doc("https://a"), _doc("https://b")]
    client = _PerUrlClient(fail_urls={"https://a", "https://b"})
    try:
        await extract_facts(docs, client=client)
        raise AssertionError("expected RateLimitError to propagate")
    except openai.RateLimitError:
        pass                                   # stream layer turns this into an error banner
    assert client.calls == 4                   # each page retried once before giving up


async def test_partial_failure_keeps_partial_results(monkeypatch):
    monkeypatch.setattr(extractor, "_RATE_LIMIT_RETRY_DELAY_S", 0)
    docs = [_doc("https://ok"), _doc("https://throttled")]
    res = await extract_facts(docs, client=_PerUrlClient(fail_urls={"https://throttled"}))
    assert len(res.facts) == 1                 # the healthy page still contributes


async def test_page_retries_once_on_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(extractor, "_RATE_LIMIT_RETRY_DELAY_S", 0)

    class _FlakyOnce:
        calls = 0
        async def complete(self, **kwargs) -> Completion:
            self.calls += 1
            if self.calls == 1:
                raise _rate_limit_error()
            return Completion(text=_ONE_FACT, prompt_tokens=5, completion_tokens=5)

    res = await extract_facts([_doc()], client=_FlakyOnce())
    assert len(res.facts) == 1                 # 429 → wait → retry → success


async def test_no_docs_returns_empty_without_raising():
    res = await extract_facts([], client=_PerUrlClient())
    assert res.facts == []
