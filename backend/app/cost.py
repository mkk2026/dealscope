"""Cost instrumentation — the engine behind the demo's headline cost-race.

Design principle (from review): the AMD number must be a CONSEQUENCE of measured
throughput, not a hardcoded slide. So `amd_rate_per_1m` is derived from the pod's
hourly cost divided by the tokens/sec you actually measure on the Instinct GPU.
That makes "$0.11 vs $2.40" reproducible and defensible, not an assertion.

Keep the comparison apples-to-apples: price the SAME model (Llama-3.1-8B) on a
hosted frontier endpoint vs on your AMD pod. That isolates the hardware/hosting
variable, which is the real Application-of-Technology claim.
"""

from dataclasses import dataclass

# Published per-1M-token USD rates. VERIFY against current provider pricing before
# the demo — these are placeholders, and a wrong number on stage is worse than none.
FRONTIER_8B_PER_1M = 0.20      # same-size model on a hosted frontier endpoint (VERIFY)
FIREWORKS_SYNTH_PER_1M = 0.90  # the AMD-hardware synthesis model on Fireworks (VERIFY)


@dataclass(frozen=True)
class StageCost:
    label: str          # "amd-pod" | "fireworks"
    tokens: int
    usd: float


def cost_usd(tokens: int, rate_per_1m: float) -> float:
    return tokens / 1_000_000 * rate_per_1m


def amd_rate_per_1m(pod_hourly_usd: float, tokens_per_sec: float) -> float:
    """Derive the AMD pod's effective $/1M tokens from measured throughput.

    pod_hourly_usd: what the Instinct pod costs per hour.
    tokens_per_sec: throughput you measured with rocm-smi / your own timing.
    """
    if tokens_per_sec <= 0:
        return 0.0
    tokens_per_hour = tokens_per_sec * 3600
    return pod_hourly_usd / tokens_per_hour * 1_000_000


@dataclass(frozen=True)
class CostRace:
    extraction_tokens: int
    amd_usd: float            # extraction on the AMD pod (derived from throughput)
    frontier_usd: float       # the SAME extraction on a hosted frontier endpoint
    synth_tokens: int
    synth_usd: float          # final memo synthesis on Fireworks
    pod_hourly_usd: float
    tokens_per_sec: float

    @property
    def total_amd_path_usd(self) -> float:
        return self.amd_usd + self.synth_usd

    @property
    def savings_x(self) -> float:
        """How many times cheaper the AMD extraction is vs frontier (the headline)."""
        return self.frontier_usd / self.amd_usd if self.amd_usd > 0 else 0.0


def compute_race(
    extraction_tokens: int,
    synth_tokens: int,
    pod_hourly_usd: float,
    tokens_per_sec: float,
) -> CostRace:
    """Build the on-screen cost comparison from real token counts + measured throughput."""
    amd_rate = amd_rate_per_1m(pod_hourly_usd, tokens_per_sec)
    return CostRace(
        extraction_tokens=extraction_tokens,
        amd_usd=cost_usd(extraction_tokens, amd_rate),
        frontier_usd=cost_usd(extraction_tokens, FRONTIER_8B_PER_1M),
        synth_tokens=synth_tokens,
        synth_usd=cost_usd(synth_tokens, FIREWORKS_SYNTH_PER_1M),
        pod_hourly_usd=pod_hourly_usd,
        tokens_per_sec=tokens_per_sec,
    )
