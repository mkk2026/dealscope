<div align="center">

# 🦄 DealScope

### Paste a startup URL. Get a source-traceable deal screen in 30 seconds.

*Autonomous public-data research with intelligent model routing on AMD-hosted GPUs.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![AMD](https://img.shields.io/badge/AMD-Instinct%20via%20Fireworks-ED1C24?logo=amd&logoColor=white)](https://fireworks.ai/)
[![Fireworks AI](https://img.shields.io/badge/Fireworks-AI-6D28D9)](https://fireworks.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-33%20passing-brightgreen)]()
[![Live Demo](https://img.shields.io/badge/▶_Live_Demo-corebrim24--dealscope.hf.space-ff4d4d)](https://corebrim24-dealscope.hf.space)

Built for the **AMD Developer Hackathon: ACT II** — Track 3 (Unicorn).

### ▶ Live demo: **[corebrim24-dealscope.hf.space](https://corebrim24-dealscope.hf.space)**

Open it, click any example screen to replay it instantly, or paste a URL to run one live.

</div>

---

## The 30-second pitch

Angel investors, VC scouts, and accelerator reviewers screen dozens of startups a
month with nothing but Google and gut instinct. They just need to answer one question
fast: **is this worth a call?**

**DealScope** answers it. Paste a company's URL and autonomous agents read its public
footprint — website, GitHub, hiring boards — and return a structured screen where
**every claim links to the source it came from**, with a confidence score.

> The wedge isn't "no input." It's **traceability**: Perplexity hallucinates and won't
> show its work; DealScope cites every line and lets you click to verify. The one
> model-opinion section (market) is labeled as such.

---

## Why it's built on AMD — the cost engine

Screening one company means reading 100+ pages — a lot of LLM calls. The trick is **not
using your most expensive model for the cheap work.** DealScope routes across two
AMD-hosted models on Fireworks:

| Stage | Model (on AMD Instinct via Fireworks) | Role |
|-------|----------------------------------------|------|
| **1 · Extract** | `gpt-oss-120b` — $0.15/$0.60 per 1M tok | Bulk page → structured facts (high volume) |
| **2 · Synthesize** | `deepseek-v4-pro` — $1.74/$3.48 per 1M tok | Verdict, risk matrix, bull/bear (one call) |

A naive pipeline uses the premium model for everything. DealScope reserves it for the
single synthesis call and routes the high-volume extraction to the cheap model:

```
   Naive (premium for every page)   ──►   $0.0337
   DealScope (routed)               ──►   $0.0095     ◄── 3.6× cheaper on real tokens
```

**The number is honest**: computed live from real input/output token counts ×
published Fireworks rates — reproducible by any judge, no estimation. The more bulk
extraction a company needs, the wider the gap. This is the hackathon's token-efficiency
thesis shipped as a product.

---

## Architecture

```
        URL
         │
         ▼
   ┌───────────┐   crawl (free, legal): site · GitHub API · job boards
   │  Collect  │──────────────────────────────────────────────────────►
   └───────────┘
         │  raw pages
         ▼
   ┌──────────────────────────┐   gpt-oss-120b (cheap) on AMD Instinct
   │  STAGE 1 · Extractor      │   page → {fact + source}, streamed live
   └──────────────────────────┘   ◄── the cost engine: high volume, low rate
         │  traceable facts
         ▼
   ┌──────────────────────────┐   deepseek-v4-pro (premium), one call
   │  STAGE 2 · Synthesizer    │   verdict · risk · scores
   └──────────────────────────┘
         │
         ▼
   Live instrument panel: streaming stages · cost-race · click-to-verify
```

One FastAPI container serves the API and the single-page UI. Runs stream over
Server-Sent Events; any run can be recorded and replayed (demo safety net).

---

## Watch it run

The UI is one page: a screener up top, and a gallery of recorded screens of recognizable
startups below — click any to replay it in the instrument panel.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env      # add your Fireworks key
uvicorn app.main:app
# open http://localhost:8000  → paste a URL, or click an example screen
```

Recorded runs ship in [`backend/demo/`](backend/demo/) so the gallery works out of the box.

## Configure `.env` (repo root, gitignored)

| Key | What it is |
|-----|------------|
| `FIREWORKS_API_KEY` | Your Fireworks key. `GET /v1/models` lists what your account can access. |
| `EXTRACT_MODEL` | Cheap, high-volume model for extraction (default `gpt-oss-120b`). |
| `SYNTH_MODEL` | Premium model for synthesis (default `deepseek-v4-pro`). |
| `GITHUB_TOKEN` | Optional — lifts the GitHub API rate limit from 60 to 5000/hr. |

> Never commit real keys. They're read from the environment at runtime only.

---

## What's under the hood

- **Source-traceable by construction** — facts carry their origin URL through the whole
  pipeline; the model never invents a source.
- **Honest failure** — a failed job-board fetch reads as *"unavailable,"* never a false
  *"0 open roles."*
- **JSON-mode + reasoning control** — Fireworks ships reasoning models, so output is
  forced to clean JSON; extraction runs gpt-oss in low-reasoning mode to stay fast/cheap.
- **Streaming + replay** — events stream as the pipeline runs; recorded runs replay
  identically.

## Tech stack

`FastAPI` · `httpx` · `BeautifulSoup` · `OpenAI SDK` · vanilla SPA + Server-Sent Events ·
AMD-hosted models via `Fireworks` · `Docker` · `pytest`

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest                # 33 unit tests (parsers, cost math, memo, collectors)
pytest -m integration # golden-company harness (hits the network)
```

## Project layout

```
backend/
  app/
    main.py            # FastAPI: /screen, /screen/stream (SSE), /api/screens, static SPA
    cost.py            # routing cost-race (naive vs routed), real Fireworks rates
    llm/client.py      # one OpenAI-compatible client; routes extract vs synth models
    pipeline/          # collect → extract → synthesize, + streaming + recorder
    static/            # the instrument-panel SPA (html/css/js)
  tests/               # unit + golden-company integration tests
  demo/                # recorded screens for the gallery / replay
  capture_gallery.py   # records the gallery screens
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
