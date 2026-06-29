# AMD Developer Cloud pod — serve Stage 1 on ROCm

Goal: a self-hosted open model answering an OpenAI-compatible endpoint on an AMD
Instinct GPU, so `AMD_BASE_URL` points at it and `test_connectivity.py` goes green.
This is THE de-risk — do it before more product code.

## 1. Provision the pod

- AMD Developer Cloud → launch a GPU pod (Instinct, e.g. MI300X).
- Pick a **ROCm + PyTorch** base image (saves you installing the stack).
- Note the pod's public IP and open inbound TCP **8000**.

## 2. Verify the GPU

SSH in, then:

```bash
rocm-smi                # should list the Instinct GPU + utilization
rocm-smi --showmeminfo vram
```

Keep `rocm-smi` handy — its utilization output is your AMD-specific demo evidence.

## 3. Serve a model (OpenAI-compatible) — two paths

**Path A — vLLM via ROCm Docker (recommended, fewest moving parts):**

```bash
docker run -d --name dealscope-llm \
  --device=/dev/kfd --device=/dev/dri \
  --group-add video --ipc=host -p 8000:8000 \
  rocm/vllm:latest \
  python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --host 0.0.0.0 --port 8000
```

Note: **Qwen2.5-7B-Instruct is not gated** — no HF token needed. Llama-3.1-8B is
gated; if you want it, set `-e HF_TOKEN=...` and accept the license on HF first.

**Path B — Ollama (simplest, fall back here if vLLM ROCm fights you):**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &                       # exposes OpenAI-compatible /v1 on :11434
ollama pull qwen2.5:7b-instruct
# then AMD_BASE_URL=http://<pod-ip>:11434/v1
```

## 4. Smoke-test on the pod

```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-7B-Instruct","messages":[{"role":"user","content":"say hi"}],"max_tokens":20}'
```

## 5. Point DealScope at it

In your repo-root `.env`:

```bash
AMD_BASE_URL=http://<pod-ip>:8000/v1
AMD_API_KEY=not-needed
AMD_MODEL=Qwen/Qwen2.5-7B-Instruct
```

Then from `backend/`:

```bash
python test_connectivity.py          # Stage 1 must read ✅
python -m app.pipeline.extractor https://linear.app   # real fact extraction
```

## 5b. Start the metrics server (makes the cost-race + GPU gauge live)

`pod/metrics_server.py` (stdlib only, no install) reads `rocm-smi` + vLLM metrics and
serves the JSON DealScope's UI needs. Copy it to the pod and run it next to vLLM:

```bash
scp pod/metrics_server.py <pod>:~/           # from your laptop
# on the pod:
python3 metrics_server.py                    # serves :9100, scrapes vLLM at :8000
```

Then point DealScope at it (repo-root `.env`):

```bash
AMD_METRICS_URL=http://<pod-ip>:9100/
```

Now the GPU gauge and tokens/sec in the demo read live off the Instinct silicon.

## 6. Measure throughput (this is the cost story)

vLLM logs tokens/sec per request. To get the *saturated* number that makes the
cost win real, fire concurrent requests and watch `rocm-smi` hit high utilization:

```bash
# rough concurrent load — count tokens/sec across N parallel calls
seq 8 | xargs -P8 -I{} curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-7B-Instruct","messages":[{"role":"user","content":"summarize: ..."}],"max_tokens":256}' >/dev/null
```

Feed `pod_hourly_usd` (your pod's rate) and measured `tokens_per_sec` into
`app.cost.compute_race`. The headline cost number falls out of those two — not a slide.

> Reminder: a tiny laptop fallback is NOT an acceptable degradation. The pod
> running on Instinct silicon is the thing that scores Application of Technology.
