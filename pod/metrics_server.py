#!/usr/bin/env python3
"""DealScope pod-side metrics server — feeds the cost-race hero with real numbers.

Run this ON the AMD pod, alongside vLLM. It reads GPU utilization from `rocm-smi`
and generation throughput from vLLM's Prometheus endpoint, and serves:

    GET /  ->  {"gpu_util": 0.0-1.0, "tokens_per_sec": <float>}

That's exactly the shape DealScope's backend reads from AMD_METRICS_URL. Point
AMD_METRICS_URL at http://<pod-ip>:9100/ and the GPU gauge + cost-race go live.

Stdlib only — no pip install needed on the pod.

    python3 metrics_server.py
    VLLM_URL=http://localhost:8000 PORT=9100 python3 metrics_server.py
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8000").rstrip("/")
PORT = int(os.environ.get("PORT", "9100"))

# Throughput is a rate, so we remember the last cumulative token count + timestamp.
_last = {"t": None, "tokens": None}


def gpu_util() -> float | None:
    """GPU busy fraction (0-1) from rocm-smi, defensive across output formats."""
    try:
        out = subprocess.run(
            ["rocm-smi", "--showuse", "--json"],
            capture_output=True, text=True, timeout=4,
        ).stdout
        data = json.loads(out)
        for _card, fields in data.items():
            for key, val in fields.items():
                if "use" in key.lower() and "%" in key:
                    pct = float(str(val).strip().rstrip("%"))
                    return max(0.0, min(1.0, pct / 100.0))
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return None


def tokens_per_sec() -> float | None:
    """Generation tokens/sec from the delta of vLLM's cumulative counter."""
    try:
        text = urllib.request.urlopen(f"{VLLM_URL}/metrics", timeout=4).read().decode()
        total = sum(
            float(m.group(1))
            for m in re.finditer(r"vllm:generation_tokens_total\S*\s+([0-9.eE+]+)", text)
        )
        now = time.monotonic()
        rate = None
        if _last["t"] is not None and now > _last["t"]:
            rate = max(0.0, (total - _last["tokens"]) / (now - _last["t"]))
        _last["t"], _last["tokens"] = now, total
        return rate
    except (urllib.error.URLError, ValueError, OSError):
        return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (stdlib API)
        payload = json.dumps({"gpu_util": gpu_util(), "tokens_per_sec": tokens_per_sec()})
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    print(f"DealScope metrics server on :{PORT}  (scraping vLLM at {VLLM_URL})")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
