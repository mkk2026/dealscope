"""One OpenAI-compatible client that fronts every model we use.

Both stages run on AMD-hosted models via Fireworks — a cheap one for bulk
extraction, a premium one for synthesis. Same client class, different model.
Token usage (input + output, separately) comes back on every call so the cost
race can be computed from real numbers.
"""

from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import settings


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, label: str):
        # Self-hosted servers often need no key; the SDK still wants a non-empty string.
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self.model = model
        self.label = label  # e.g. "amd-pod" or "fireworks" — used in cost reporting

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_mode: bool = False,
        reasoning_effort: str | None = None,
    ) -> Completion:
        # JSON mode forces valid-JSON output, which stops reasoning models from
        # leaking chain-of-thought into the answer. reasoning_effort="low" keeps
        # gpt-oss fast + cheap for the high-volume extraction stage. Fireworks
        # honors both; unknown params are ignored by models that don't use them.
        extra: dict = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            extra["reasoning_effort"] = reasoning_effort
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        usage = resp.usage
        return Completion(
            text=resp.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


def extractor_client() -> LLMClient:
    """Stage 1 — the cheap, high-volume model (gpt-oss-120b) on AMD via Fireworks."""
    return LLMClient(
        base_url=settings.fireworks_base_url,
        api_key=settings.fireworks_api_key,
        model=settings.extract_model,
        label="extract",
    )


def synthesis_client() -> LLMClient:
    """Stage 2 — the premium model (deepseek-v4-pro) on AMD via Fireworks."""
    return LLMClient(
        base_url=settings.fireworks_base_url,
        api_key=settings.fireworks_api_key,
        model=settings.synth_model,
        label="synth",
    )
