"""Cost-race engine: naive single-model vs DealScope's routed approach.

Both run on AMD-hosted models via Fireworks. The number is computed from REAL
input/output token counts times published Fireworks per-1M-token rates — no
estimation, fully reproducible by a skeptical judge.

The thesis: extraction is the high-volume stage (100+ pages). Route it to a cheap
AMD model (gpt-oss-120b) and reserve the premium model (deepseek-v4-pro) for the
single synthesis call. A naive pipeline uses the premium model for everything.

Rates: USD per 1M tokens, Fireworks serverless standard tier (2026-06).
Source: docs.fireworks.ai/serverless/pricing  — VERIFY before the demo.
"""

from dataclasses import dataclass

# Cheap model — bulk extraction (gpt-oss-120b).
EXTRACT_IN_PER_1M = 0.15
EXTRACT_OUT_PER_1M = 0.60
# Premium model — synthesis, and the "naive everything" baseline (deepseek-v4-pro).
SYNTH_IN_PER_1M = 1.74
SYNTH_OUT_PER_1M = 3.48


def _cost(tok_in: int, tok_out: int, rate_in: float, rate_out: float) -> float:
    return tok_in / 1_000_000 * rate_in + tok_out / 1_000_000 * rate_out


@dataclass(frozen=True)
class CostRace:
    extract_in: int
    extract_out: int
    synth_in: int
    synth_out: int

    @property
    def routed_usd(self) -> float:
        """Cheap model for extraction, premium for synthesis — what DealScope does."""
        return (_cost(self.extract_in, self.extract_out, EXTRACT_IN_PER_1M, EXTRACT_OUT_PER_1M)
                + _cost(self.synth_in, self.synth_out, SYNTH_IN_PER_1M, SYNTH_OUT_PER_1M))

    @property
    def naive_usd(self) -> float:
        """Premium model for everything — the baseline DealScope beats."""
        return (_cost(self.extract_in, self.extract_out, SYNTH_IN_PER_1M, SYNTH_OUT_PER_1M)
                + _cost(self.synth_in, self.synth_out, SYNTH_IN_PER_1M, SYNTH_OUT_PER_1M))

    @property
    def savings_x(self) -> float:
        return self.naive_usd / self.routed_usd if self.routed_usd > 0 else 0.0

    @property
    def total_tokens(self) -> int:
        return self.extract_in + self.extract_out + self.synth_in + self.synth_out


def compute_race(extract_in: int, extract_out: int,
                 synth_in: int = 0, synth_out: int = 0) -> CostRace:
    return CostRace(extract_in, extract_out, synth_in, synth_out)
