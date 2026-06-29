"""One OpenAI-compatible client that fronts every model we use.

The self-hosted AMD-pod model (vLLM/Ollama) and Fireworks both speak the
OpenAI chat-completions API, so a single client class — pointed at different
base URLs — covers all three stages. Token usage comes back on every call so
the UI can show the AMD-vs-frontier cost story.
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
    ) -> Completion:
        # JSON mode forces valid-JSON output, which is what stops these reasoning
        # models from leaking chain-of-thought into the answer. vLLM and Fireworks
        # both honor response_format.
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
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
    """Stage 1 — the cheap, high-volume workhorse on the AMD GPU pod."""
    return LLMClient(
        base_url=settings.amd_base_url,
        api_key=settings.amd_api_key,
        model=settings.amd_model,
        label="amd-pod",
    )


def synthesis_client() -> LLMClient:
    """Stages 2-3 — the premium model on Fireworks (AMD hardware)."""
    return LLMClient(
        base_url=settings.fireworks_base_url,
        api_key=settings.fireworks_api_key,
        model=settings.fireworks_model,
        label="fireworks",
    )
