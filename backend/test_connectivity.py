"""De-risk script: prove both model endpoints answer before building anything else.

This is the single most important thing to get green. If the AMD pod responds
here, the whole DealScope cost-engine strategy is real. Run it from backend/:

    python test_connectivity.py

It hits Stage 1 (AMD-hosted model) and Stages 2-3 (Fireworks) independently,
so a failure on one doesn't hide a success on the other.
"""

import asyncio

from app.llm.client import extractor_client, synthesis_client


async def _probe(name: str, make_client) -> None:
    print(f"\n── {name} ──")
    try:
        client = make_client()
        print(f"  base_url : {client._client.base_url}")
        print(f"  model    : {client.model}")
        result = await client.complete(
            system="You are a terse health check. Reply with exactly one short sentence.",
            user="Say 'DealScope connectivity OK' and name yourself.",
            max_tokens=40,
        )
        print(f"  reply    : {result.text.strip()}")
        print(f"  tokens   : {result.total_tokens} "
              f"(prompt {result.prompt_tokens} / completion {result.completion_tokens})")
        print(f"  STATUS   : ✅ OK")
    except Exception as exc:  # noqa: BLE001 — we want to see any failure plainly
        print(f"  STATUS   : ❌ FAILED — {type(exc).__name__}: {exc}")


async def main() -> None:
    print("DealScope endpoint connectivity check")
    await _probe("Stage 1: AMD-hosted model (vLLM/Ollama on Instinct pod)", extractor_client)
    await _probe("Stages 2-3: Fireworks (AMD hardware)", synthesis_client)
    print("\nDone. Both must read ✅ before building the pipeline.")


if __name__ == "__main__":
    asyncio.run(main())
