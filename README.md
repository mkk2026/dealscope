<div align="center">

# 🦄 DealScope

### Paste a startup URL. Get a source-traceable deal screen in 30 seconds.

*Autonomous public-data research with an AMD GPU as the cost engine.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![AMD ROCm](https://img.shields.io/badge/AMD-Instinct%20%2F%20ROCm-ED1C24?logo=amd&logoColor=white)](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html)
[![Fireworks AI](https://img.shields.io/badge/Fireworks-AI-6D28D9)](https://fireworks.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-33%20passing-brightgreen)]()

Built for the **AMD Developer Hackathon: ACT II** — Track 3 (Unicorn).

</div>

---

## The 30-second pitch

Angel investors, VC scouts, and accelerator reviewers screen dozens of startups a
month with nothing but Google and gut instinct. They don't get a data room until
*after* the first meeting. They just need to answer one question fast: **is this
worth a call?**

**DealScope** answers it. Paste a company's URL and autonomous agents read its public
footprint — website, GitHub, hiring boards — and return a structured screen where
**every claim links to the source it came from**, with a confidence score. Not "AI
due diligence." An honest, verifiable pre-meeting screen.

> The wedge isn't "no input." It's **traceability**: Perplexity hallucinates and
> won't show its work; DealScope cites every line and lets you click to verify.

---

## Why it's built on AMD

This is the part that matters. Screening one company means reading 100+ pages — a lot
of LLM calls. DealScope splits the work so the **AMD GPU is the cost engine**, not a logo:

| Stage | Runs on | Job |
|-------|---------|-----|
| **1 · Extract** | Self-hosted open model on an **AMD Instinct GPU pod** (ROCm + vLLM) | Bulk page → structured facts, each tagged with its source URL |
| **2 · Synthesize** | Fireworks AI (AMD-hardware models) | Verdict, risk matrix, bull/bear over *only* traceable facts |

```
        URL
         │
         ▼
   ┌───────────┐   crawl (free, legal): site · GitHub API · job boards
   │  Collect  │──────────────────────────────────────────────────────►
   └───────────┘
         │  raw pages
         ▼
   ┌──────────────────────────┐   measure tokens/sec here —
   │  STAGE 1 · Extractor      │   self-hosted on AMD Instinct (ROCm/vLLM)
   │  page → {fact + source}   │   bulk, batched, cheap   ◄── the cost engine
   └──────────────────────────┘
         │  traceable facts
         ▼
   ┌──────────────────────────┐
   │  STAGE 2 · Synthesizer    │   Fireworks (AMD-hardware model)
   │  verdict · risk · scores  │
   └──────────────────────────┘
         │
         ▼
   Live instrument panel: streaming stages · cost-race · GPU gauge · click-to-verify
```

**The hero metric, proven from measured throughput** (`app/cost.py`): bulk extraction
runs on the saturated AMD pod for cents while a hosted endpoint costs multiples more —
a live cost-race ticks on screen next to a real `rocm-smi` GPU-utilization gauge. The
number is a *consequence of measured tokens/sec*, not a slide.

---

## Watch it run

The UI is a live **instrument panel**: stage cards light up, the cost-race ticks, the
GPU gauge climbs, the memo streams in, and every fact is a clickable link to its source.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Replay a recorded run (no keys needed) — the fastest way to see the whole flow:
uvicorn app.main:app
# then open:  http://localhost:8000/?replay=events-linear.app.jsonl
```

A real recorded run ships in [`backend/demo/`](backend/demo/) — 29 real facts about
Linear with a "Worth a call — 75/100" verdict.

---

## Quickstart (live)

```bash
cd backend
cp ../.env.example ../.env       # then fill in your keys (see below)
pip install -r requirements.txt
uvicorn app.main:app
# open http://localhost:8000 → paste a URL → Screen
```

Configure `.env` at the repo root (it is gitignored — never commit real keys):

| Key | What it is |
|-----|------------|
| `FIREWORKS_API_KEY` / `FIREWORKS_MODEL` | Stage 2 synthesis. `GET /v1/models` lists what your account can access. |
| `AMD_BASE_URL` / `AMD_MODEL` | Stage 1 on the pod — the vLLM OpenAI endpoint (`http://<pod-ip>:8000/v1`). |
| `AMD_METRICS_URL` | The pod metrics server (`pod/metrics_server.py`) — makes the GPU gauge live. |
| `GITHUB_TOKEN` | Optional — lifts the GitHub API rate limit from 60 to 5000/hr. |

Standing up the AMD pod (ROCm + vLLM + the metrics server) is a copy-paste walkthrough:
**[docs/amd-pod-setup.md](docs/amd-pod-setup.md)**.

---

## What's under the hood

- **Source-traceable by construction** — facts carry their origin URL through the whole
  pipeline; the model never invents a source. The one model-opinion section (market) is
  labeled as such.
- **Honest failure** — a failed job-board fetch reads as *"unavailable,"* never a false
  *"0 open roles."* Estimates are flagged, not asserted.
- **JSON-mode everywhere** — Fireworks ships reasoning models, so output is forced to clean
  JSON to keep chain-of-thought out of the memo.
- **Streaming over SSE** — one container serves the API and the SPA; events stream as the
  pipeline runs. Runs can be recorded and replayed (demo safety net).

## Tech stack

`FastAPI` · `httpx` · `BeautifulSoup` · `OpenAI SDK` (any compatible endpoint) ·
vanilla SPA + Server-Sent Events · `vLLM` on `ROCm` · `Docker` · `pytest`

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest                          # 33 unit tests (parsers, cost math, memo, collectors)
pytest -m integration           # golden-company harness (hits the network)
```

## Project layout

```
backend/
  app/
    main.py            # FastAPI: /screen, /screen/stream (SSE), static SPA
    cost.py            # throughput-derived cost-race engine
    llm/client.py      # one OpenAI-compatible client for pod + Fireworks
    pipeline/          # collect → extract → synthesize, + streaming + recorder
    static/            # the instrument-panel SPA (html/css/js)
  tests/               # unit + golden-company integration tests
  demo/                # recorded runs for replay
pod/metrics_server.py  # runs ON the AMD pod: rocm-smi + vLLM → cost-race feed
docs/amd-pod-setup.md  # ROCm + vLLM walkthrough
DESIGN-*.md            # product + demo design docs
```

## Containerized

```bash
cd backend
docker build -t dealscope .
docker run -p 8080:8080 --env-file ../.env dealscope
```

---

## License

[MIT](./LICENSE) — original work for the AMD Developer Hackathon: ACT II.
