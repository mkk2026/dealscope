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


@dataclass
class Verdict:
    recommendation: str   # "Worth a call" | "Borderline" | "Pass"
    score: int            # 0-100
    bull: str
    bear: str


@dataclass
class Memo:
    """The deal screen. Facts are sourced (traceable); summaries/risk/verdict are
    model synthesis over those facts. section_summaries['market'] is opinion."""
    url: str
    section_summaries: dict[str, str] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    risk_matrix: list[Risk] = field(default_factory=list)
    verdict: Verdict | None = None
    confidence: int = 0
