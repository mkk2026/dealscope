"""Environment-based configuration. Secrets are read from the environment / .env,
never hardcoded. See .env.example for the full list."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the repo root (two levels up from this file) so it loads no
# matter the CWD — uvicorn runs from backend/, scripts run from elsewhere.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Stage 1 — bulk extraction on a self-hosted model (AMD Instinct GPU pod).
    amd_base_url: str = "http://localhost:8000/v1"
    amd_api_key: str = "not-needed"
    amd_model: str = "Qwen/Qwen2.5-7B-Instruct"  # non-gated; Llama-3.1-8B needs HF license

    # Stages 2-3 — Fireworks AI (AMD-hardware models).
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_api_key: str = ""
    fireworks_model: str = "accounts/fireworks/models/deepseek-v4-pro"

    # Optional — a GitHub token lifts the public API rate limit from 60 to 5000/hr.
    # Read-only / public scope is plenty. Leave blank to run unauthenticated.
    github_token: str = ""

    # Crawl politeness knobs.
    crawl_max_pages: int = 8
    crawl_concurrency: int = 5
    http_timeout: float = 15.0

    # Extraction knobs.
    extract_max_chars: int = 6000   # per-page text cap sent to the model
    extract_concurrency: int = 4    # parallel extraction calls to the pod

    # Cost-race demo inputs. Real values arrive once the pod is up; until then these
    # are flagged placeholders so the hero renders, and the recorded run carries truth.
    amd_pod_hourly_usd: float = 2.00
    amd_assumed_tokens_per_sec: float = 1500.0
    amd_metrics_url: str = ""        # optional pod endpoint: {"gpu_util":0-1,"tokens_per_sec":N}


settings = Settings()
