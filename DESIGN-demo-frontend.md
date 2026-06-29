# DealScope — Demo + Frontend Design

**For:** AMD Developer Hackathon ACT II, Track 3. The 60-90s judge moment.
**Date:** 2026-06-27
**Status:** Approved (office-hours). Hero = cost-race + GPU working. Stack = lean SSE single-page, instrument-panel framing.

> This designs the demo; it is not built yet. Backend pipeline already works end-to-end
> (see [DESIGN-dealscope.md](DESIGN-dealscope.md)).

---

## The hero moment

**A live cost-race next to a working AMD GPU.** While DealScope screens a company, the
screen shows two cost counters ticking — "Hosted endpoint: \$X │ DealScope on AMD: \$Y" —
beside a live GPU-utilization gauge and a tokens/sec readout pulled straight from the
Instinct pod. That single frame is the slide. It scores Application of Technology (the
axis this track is won on) because it shows the silicon doing the work, not a dollar
ratio asserted on a slide.

**Non-negotiable: the numbers are real.** Tokens/sec and GPU util come from the pod
during the run (vLLM `/metrics`, `rocm-smi`). A faked counter dies the instant a judge
asks "is that live?"

**Demo safety: record one real run and be able to replay it.** Live is best, but a pod
hiccup mid-demo can't be allowed to kill the hero. We capture one genuine run's event
stream to a file and can replay it through the exact same UI. It's real data, just
pre-recorded — honest, and it means a network blip can't sink the demo.

---

## The 90-second script (beat by beat)

1. **0-5s** — Clean screen, one input. Type a real company (`linear.app`). Hit **Screen**.
2. **5-15s** — Input collapses; the **instrument panel** takes over. Stage cards light up:
   Collect → Extract (AMD) → Synthesize (Fireworks). "Collected 9 sources... extracting..."
3. **15-45s — THE HERO.** Center stage: the **cost-race** counters tick as extraction runs,
   the **GPU-util gauge** climbs and pulses, **tokens/sec** reads live off the pod. Slow down
   here. This is the screenshot. Narrate: "150 pages of extraction, running on AMD Instinct —
   watch the GPU saturate. Same work on a hosted endpoint would cost N times more."
4. **45-70s** — The **memo** streams in underneath: verdict big and bold ("Worth a call —
   70/100"), bull/bear, sections filling with facts.
5. **70-85s — the kill shot.** Click a claim ("1,464 stars"). It opens the real GitHub page.
   "Every line, traceable. Nothing here you can't verify." Note the Market section is
   labeled *model opinion* — we don't fake sources.
6. **85-90s** — One-line close + the cost number on screen. Done.

---

## Frontend architecture (A + C)

**One container.** FastAPI serves both the API and a single static `index.html`
(+ one JS + one CSS file). No separate Next.js service, no node build — fewer things to
break live, clean submission.

```
Browser (instrument-panel SPA)
   │  POST /screen/stream  (Server-Sent Events)
   ▼
FastAPI
   ├── runs pipeline: collect → extract (AMD) → synthesize (Fireworks)
   ├── samples pod metrics during extract (vLLM /metrics + rocm-smi)
   └── emits SSE events as each thing happens
```

### SSE event protocol (the back/front contract)

Backend emits newline-delimited JSON events on `/screen/stream?url=...`:

```jsonc
{"type":"stage",  "stage":"collect",   "status":"done", "sources":9}
{"type":"stage",  "stage":"extract",   "status":"start"}
{"type":"metric", "tokens_per_sec":880, "gpu_util":0.93, "cum_tokens":120000}
{"type":"cost",   "amd_usd":0.11, "frontier_usd":2.40, "savings_x":21.8}
{"type":"fact",   "category":"engineering","claim":"1,464 stars","source_url":"https://github.com/linear/linear","confidence":0.8}
{"type":"stage",  "stage":"synthesize","status":"done"}
{"type":"memo",   "verdict":{"recommendation":"Worth a call","score":70,"bull":"...","bear":"..."},"risk_matrix":[...],"confidence":60}
{"type":"done"}
```

`fact` events stream as extraction finds them (drives both the live "facts found" count and
the click-to-verify list). `metric`/`cost` events drive the hero. Client animates/interpolates
between metric samples so counters move smoothly, not in jumps.

### Backend additions needed

1. **`/screen/stream` endpoint** — `StreamingResponse(media_type="text/event-stream")`. Set
   `Cache-Control: no-cache`, `X-Accel-Buffering: no` so nothing buffers the stream.
2. **Per-stage/per-page emit** — `extract_facts` takes an optional `on_event` callback so it
   can emit a `fact`/`metric` event per page instead of only returning at the end.
3. **Metrics sampler** — during extraction, poll the pod: vLLM `/metrics` (Prometheus, has
   tokens/sec) and a tiny pod-side endpoint running `rocm-smi --json` for GPU util. Emit
   `metric` events ~2-4x/sec. Cost events computed via `app/cost.py` from live tokens/sec.
4. **Recorder + replay** — wrap the event stream so a real run can be written to
   `demo/events-<company>.jsonl`. `/screen/stream?replay=<file>` re-emits that file with the
   original timing. Same renderer, zero UI difference.

### The instrument-panel layout

```
┌─────────────────────────────────────────────────────────┐
│  DealScope    [ linear.app............ ]  ( Screen )      │  ← collapses after start
├───────────────┬─────────────────────────────────────────┤
│ PIPELINE      │            ★ COST RACE ★                 │
│ ● Collect  9  │   Hosted:  $2.40   ┌───────────────┐     │
│ ● Extract ▓▓  │   AMD:     $0.11   │ GPU util  93% │     │  ← HERO (center, big)
│ ○ Synthesize  │   savings: 21.8×   │ ▁▃▅▇█▇▅  tok/s│     │
│   facts: 23   │                    └──── 880 ──────┘     │
├───────────────┴─────────────────────────────────────────┤
│  VERDICT: Worth a call — 70/100        confidence 60     │  ← memo (after run)
│  bull: ...   bear: ...                                   │
│  [engineering] 1,464 stars ↗ (click → github.com/...)   │  ← click-to-verify
│  [market] (model opinion) crowded space...              │
└─────────────────────────────────────────────────────────┘
```

Hero is center and large. Pipeline cards are the supporting "it's alive" act. Memo +
click-to-verify is the payoff. GPU gauge + sparkline are hand-rolled canvas — full control,
no chart-lib dependency.

---

## Build plan (next session)

| Step | Deliverable |
|------|-------------|
| 1 | `/screen/stream` SSE endpoint emitting coarse stage events over the existing pipeline |
| 2 | Single-page instrument panel: stage cards + memo + click-to-verify, consuming SSE |
| 3 | The hero: cost counters + GPU gauge + tokens/sec sparkline (canvas), fed by metric/cost events |
| 4 | `extract_facts` per-page `on_event` callback → live fact/metric streaming |
| 5 | Metrics sampler (vLLM `/metrics` + pod `rocm-smi`) — needs the pod up |
| 6 | Recorder + `?replay=` mode; capture one real run; lock 3 demo companies |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Pod down at demo time kills the live hero | The recorded-run replay mode is the safety net. Capture it early. |
| SSE gets buffered by a proxy → no live feel | Set no-cache + `X-Accel-Buffering: no`; test in the actual demo browser/network. |
| Live counters look janky | Client-side interpolate between metric samples; ease the animation. |
| Hero overshadows the verdict (style over substance) | Verdict lands big right after the hero; click-to-verify is the substance proof. |
| Per-page streaming needs pipeline changes | Single `on_event` callback through `extract_facts` — small, additive. |

---

## THE ASSIGNMENT

**The moment the pod is serving, capture one real end-to-end run's event stream to
`demo/events-linear.jsonl`.**

That one artifact is both halves of the win: it's the recorded fallback that makes the demo
un-killable, and it's the real GPU/tokens data that proves the hero isn't a gimmick. Everything
else in the frontend renders the same whether it's reading a live stream or that file — so the
day you have that capture, your demo is effectively done and de-risked. It also forces the pod
(still the critical-path item from [docs/amd-pod-setup.md](docs/amd-pod-setup.md)) to the front
of the queue, where it belongs.
