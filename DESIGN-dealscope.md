# DealScope — Design Doc

**Hackathon:** AMD Developer Hackathon: ACT II — Track 3 (Unicorn)
**Date:** 2026-06-23
**Status:** Approved direction (Approach A + C)

---

## One-liner

> Paste a startup's URL. DealScope reads its public footprint and returns a **source-traceable 30-second deal screen** — every claim links to where it came from, with a confidence score — built on an AMD GPU cost engine that does the work for cents.

Not "AI due diligence." The honest, defensible claim: **the pre-first-meeting screen.** "Is this worth 45 minutes?" — answered in 30 seconds, with receipts.

---

## The wedge (why this is defensible)

The category (URL-in → company-research-out) is crowded: Perplexity, ChatGPT browsing, Clay, Harmonic, Specter, Crunchbase. We do **not** claim novelty of the category. We win on one sharp, true difference:

**Every line in the memo is traceable to a public source, with a confidence score, and you can click to verify it live.**

Perplexity hallucinates and won't show its work. ChatGPT gives prose, not a structured screen. We give a structured verdict where a skeptical judge can click any claim and land on the GitHub page / job board / press article it came from. That is the moment we win Originality honestly — on stage, in front of people who will try to catch us.

---

## The AMD cost engine (this is how we win Application of Technology)

Track 3 explicitly allows self-hosting any open-source model on an AMD Developer Cloud GPU pod **plus** Fireworks. Most teams will ignore this and just call Fireworks. We make the AMD GPU load-bearing:

**Two-stage pipeline** (collapsed from 3 in /autoplan review — the old "Researcher" stage produced unsourced market prose that contradicted the traceability wedge):

| Stage | Where it runs | Job |
|-------|---------------|-----|
| 1. Extractor | **Self-hosted open model (Llama 3.1 8B / Qwen) on AMD Instinct GPU pod** | High-volume grunt work: read 100+ crawled pages, extract structured facts, each with its source URL |
| 2. Synthesizer | Fireworks (AMD-hardware model) | Final memo over only-traceable facts: bull/bear, risk matrix, verdict. Market Position is clearly labeled "model opinion, not sourced." |

**The hero metric — and the honest caveat (proven in `app/cost.py`):**
> "Screening one company touches ~150 public pages. We run bulk extraction on a self-hosted model on AMD Instinct and spend Fireworks budget only on the final memo."

The cost win is **real but conditional on throughput**. Same-size model (8B) on a cheap hosted endpoint can beat a single-stream pod — the pod only wins once you **saturate it** (batch concurrent extractions so the hourly cost amortizes across high tokens/sec). So the on-screen number must come from *measured* throughput, not a slide. Two ways to make it credible:
1. **Saturate the pod** — batch the 150-page extraction, measure real tokens/sec with `rocm-smi`, derive cost from that (see `compute_race`).
2. **Show the GPU working** — `rocm-smi` utilization graph + tokens/sec on the Instinct part. That is the AMD-specific evidence that scores **Application of Technology**, which a portable "$ ratio" alone does not.

This also solves the "$50 Fireworks runs out during dev" risk for free — bulk work never hits Fireworks.

---

## Architecture

```
        URL
         │
         ▼
   ┌───────────┐     crawl (free, legal)
   │  Crawler  │────► company site, GitHub API, public job boards
   └───────────┘      (Greenhouse/Lever/Ashby), HN/news search, reviews
         │  raw pages (100+)
         ▼
   ┌──────────────────────────┐
   │  STAGE 1: Extractor       │  Self-hosted Llama/Qwen on AMD GPU pod
   │  page → {facts + source}  │  Bulk, batched, every fact carries its URL
   └──────────────────────────┘  (measure tokens/sec here — it's the cost story)
         │  structured facts (traceable)
         ▼
   ┌──────────────────────────┐
   │  STAGE 2: Synthesizer     │  Fireworks (AMD-hardware model)
   │  memo + verdict + scores  │  over only-traceable facts; market = labeled opinion
   └──────────────────────────┘
         │
         ▼
   Streaming UI: agents working live → memo builds section by section
   → every claim is a clickable source link → cost counter ticking
```

**Stack:** FastAPI backend, Next.js frontend, Docker (submission requires containerized). AMD Developer Cloud pod hosts the Stage-1 model (vLLM or Ollama on ROCm). Fireworks for Stage 2 (synthesis).

---

## Data sources — free and legal only

Source ONLY what we can get reliably and verifiably. Anything we can't source cleanly does **not** go in the live demo.

| Signal | Source | Status |
|--------|--------|--------|
| Product / pricing / positioning | Company website crawl | ✅ Easy, real |
| Engineering health | GitHub public API (repos, contributors, stars, commit velocity) | ✅ Easy, real, free |
| Hiring momentum | Public job boards (Greenhouse / Lever / Ashby) + careers page | ✅ Scrapeable, real |
| Press / traction | News + HN search API | ✅ Real |
| Product sentiment | Public reviews (G2/Capterra/Product Hunt where available) | ⚠️ Partial |
| Web traffic growth | SimilarWeb-class | ❌ Paid + anti-scraping — **cut from demo** |
| Founder prior exits | LinkedIn | ❌ Auth-walled + anti-bot — **cut from demo** |

Estimated/uncertain data gets labeled **"estimated, low confidence"** in the UI. That labeling *builds* trust rather than risking a falsifiable number on stage.

---

## Memo output (the deliverable)

Structured screen, each section streams in, each claim is a clickable source:

1. **Company Overview** — what they do, who for, pricing model
2. **Engineering Audit** — GitHub health, velocity, stack signals
3. **Hiring Signal** — open roles, seniority mix, what it implies
4. **Market Position** — competitors, differentiation. **Labeled "model opinion, not sourced"** — it's the one section that isn't claim-by-claim traceable, so it must not undercut the trust story.
5. **Traction Signals** — press, community, reviews
6. **Risk Matrix** — 5 categories scored 1-10 with reasons
7. **The Verdict** — Worth a call? bull case / bear case / one-line recommendation
8. **Confidence Score** — overall 0-100 + per-section, every source linked

---

## Demo script (60-90 seconds, this is what judges remember)

1. Clean UI, one input. Type a real company (`linear.app`). Hit **Screen**.
2. Two stage cards light up live: Extractor (AMD pod) chewing through pages, then Synthesizer.
3. **Cost counter ticks in the corner the whole time**, fed by *measured* tokens/sec. Split readout: "Same extraction, hosted endpoint: $X │ DealScope on AMD (saturated): $Y." Pair it with a small `rocm-smi` utilization readout so judges see the silicon working.
4. Memo builds section by section. Verdict lands: "Worth a call — 84/100."
5. **The kill shot:** click any claim. It opens the exact GitHub page / job posting / article it came from. "Every line, traceable. No hallucinations you can't check."
6. One-click PDF export.

The cost split + the click-to-verify are the two moments. Rehearse them until they're flawless.

---

## Build plan (rebuilt around the REAL runway)

Key correction to the original plan: **Track 3 has no kickoff-revealed tasks** (that's Track 1). Today is June 23. Kickoff is July 6. So the two weeks of "prep" are build time. Walk into July 6 with a working core; spend the event polishing.

| Window | Focus | Deliverable |
|--------|-------|-------------|
| **Jun 23-26** | Foundation | AMD Developer Cloud pod provisioned, Stage-1 model self-hosted (vLLM/Ollama on ROCm) and serving, Fireworks connected, FastAPI + Next.js skeleton, Docker building |
| **Jun 27-30** | Core loop | Crawler + GitHub API + 1 job board working. Stage-1 extraction producing traceable facts end-to-end. Single-section memo rendering. |
| **Jul 1-3** | Full pipeline | Stage 2 synthesis, all sections, risk matrix, verdict, confidence scoring. Cost instrumentation (`app/cost.py`) wired into UI. Eval set running. |
| **Jul 4-5** | Polish | Streaming agent UI, click-to-verify links, cost-race readout, PDF export. Test against 8-10 real companies. |
| **Jul 6-9** | Event + hardening | Attend kickoff, fix edge cases, lock the demo against your best 3 test companies, finalize container. |
| **Jul 10-11** | Submit | Video, slides, cover image, public GitHub repo, hosted demo URL. Submit before deadline. |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| AMD pod setup eats day 1-2 | Start it **today**. ROCm self-hosting is the one unknown — de-risk first. The pod is **non-negotiable, not gracefully degradable**: falling back to a tiny laptop model is also "off-Fireworks" but kills the AMD Application-of-Technology score, which is the track's primary axis. |
| Cost story read as a gimmick | Derive the number from *measured* tokens/sec (`app/cost.py`), saturate the pod, and show `rocm-smi`. A portable "$ ratio" alone scores ~nothing on AMD hardware use. |
| Crawling unreliable on some sites | Multiple fallbacks per signal; fail gracefully ("data unavailable," never an error). Verified `linear.app` crawls clean; verify all 3 demo companies. |
| Live demo claim gets falsified | Only source free/verifiable signals. Job-board fetch failures now read as "unavailable," not "0 roles." Every on-screen number clickable to its source. |
| Judges hold "due diligence" to VC standard | We never say due diligence. We say "deal screen / worth a call." |

---

## Evals (added in /autoplan review — your demo safety net)

A traceability product that confidently cites a *wrong* fact is worse than prose. Before the demo you need accuracy you can point to.

- **Golden set:** 8-10 companies you can verify by hand (mix of has-GitHub / no-GitHub, has-board / no-board). Include your 3 demo companies.
- **Ground truth:** for each, a small hand-checked list of expected facts (real GitHub org, real open-role count, real pricing tiers).
- **Harness:** `pytest` that runs `collect()` (and later the full pipeline) on all of them and asserts the right entity was found, no section is empty, and extracted facts match ground truth. Doubles as the "which companies are stage-safe" check.
- **Collector unit tests:** fixture-based tests for `extract_github_org`, `detect_boards`, and each ATS JSON shape (Greenhouse/Lever/Ashby) so a provider schema change can't silently break the demo.

## /autoplan review record (2026-06-24)

Ran CEO + Eng review. Codex voice unavailable (expired auth); one independent Claude voice + primary review. Both converged on: AMD story must be silicon not arithmetic; cost must be measured; evals missing; frontend is the unbuilt critical path.

**Applied:** `.env` path fix (unblocked the de-risk tool), GitHub org disambiguation + 403/404 split, job-board fetch-fail vs zero-roles, crawler concurrency cap + cross-page link discovery, collector failure logging, `app/cost.py` (throughput-derived cost), 3→2 stage collapse, Market Position labeled opinion.

**Still open (sequenced):** stand up the AMD pod (THE assignment), build the 2-stage pipeline, the streaming frontend, the eval set, and the demo artifacts (video/slides/hosted URL).

---

## What I noticed (founder signals)

You came in with a fully-researched plan, took direct pushback on five premises without getting defensive, and asked for the version that wins rather than the version that flatters. That's the right instinct. The plan's weakness was never ambition — it was a thin AMD story wrapped in an overclaimed "nobody does this." Both fixable, both fixed.

---

## THE ASSIGNMENT (do this before writing product code)

**Provision the AMD Developer Cloud pod today and get one open model (Llama 3.1 8B or Qwen) self-hosted and answering a single test prompt over HTTP on ROCm.**

That is the one unknown that the entire winning narrative rests on. Everything else (FastAPI, Next.js, crawling, Fireworks calls) you already know how to build. If the AMD GPU serving works, you have a moat no other Track 3 team will bother to build. If it fights you, you need to know that on June 23, not July 4. Prove the hard part first.
