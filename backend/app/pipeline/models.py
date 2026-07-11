"""Shared data shapes for the pipeline.

Everything the crawler/fetchers produce is a SourceDocument carrying its origin
URL. That URL is what makes every downstream fact click-to-verify — the whole
trust story rests on never losing it.
"""

from dataclasses import dataclass, field
from enum import Enum


class SourceKind(str, Enum):
    WEBPAGE = "webpage"
    GITHUB = "github"
    JOBS = "jobs"


@dataclass
class SourceDocument:
    url: str
    kind: SourceKind
    title: str
    text: str
    meta: dict = field(default_factory=dict)

    def preview(self, n: int = 120) -> str:
        body = self.text.strip().replace("\n", " ")
        return body[:n] + ("…" if len(body) > n else "")


# The memo sections a fact can belong to. Market is model-opinion, kept separate.
CATEGORIES = ("overview", "engineering", "hiring", "market", "traction")


@dataclass
class Fact:
    """One atomic, verifiable claim. source_url is attached by us (from the
    SourceDocument), never trusted from the model — that's what keeps it traceable."""
    claim: str
    category: str
    source_url: str
    confidence: float


@dataclass
class Risk:
    category: str
    score: int        # 1-10, higher = riskier
    reason: str


# The investor scorecard — the signals a deal-screener actually weighs, in display
# order. The ids are the contract between prompt, validator, and UI.
SCORECARD_SIGNALS = {
    "technical_team": "Technical team",
    "hiring_velocity": "Hiring velocity",
    "shipping_cadence": "Shipping cadence",
    "customer_evidence": "Customer evidence",
    "revenue_signals": "Revenue signals",
    "github_momentum": "GitHub momentum",
    "market_timing": "Market timing",
    "moat_evidence": "Moat evidence",
    "capital_efficiency": "Capital efficiency",
    "red_flags": "Red flags",
}


@dataclass
class Signal:
    """One investor-screening signal. evidence holds source URLs drawn from the
    collected facts — a signal that cannot cite a collected source is downgraded
    to insufficient_data, never scored on faith."""
    id: str
    name: str
    score: int                # 0-10; for red_flags higher = more red flags
    rationale: str
    evidence: list[str] = field(default_factory=list)
    status: str = "scored"    # "scored" | "insufficient_data"


@dataclass
class Verdict:
    recommendation: str   # "Worth a call" | "Borderline" | "Pass"
    score: int            # 0-100
    bull: str
    bear: str


@dataclass
class Memo:
    """The deal screen. Facts are sourced (traceable); summaries/risk/verdict are
    model synthesis over those facts. section_summaries['market'] is opinion.
    scorecard signals cite fact source URLs — validated, never trusted from the model."""
    url: str
    section_summaries: dict[str, str] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    risk_matrix: list[Risk] = field(default_factory=list)
    verdict: Verdict | None = None
    confidence: int = 0
    scorecard: list[Signal] = field(default_factory=list)
