"""Environment-based configuration. Secrets are read from the environment / .env,
never hardcoded. See .env.example for the full list."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the repo root (two levels up from this file) so it loads no
# matter the CWD — uvicorn runs from backend/, scripts run from elsewhere.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Both stages run on AMD-hosted models via Fireworks. The routing IS the product:
    # bulk extraction on a cheap model, synthesis on a premium one.
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_api_key: str = ""
    extract_model: str = "accounts/fireworks/models/gpt-oss-120b"      # cheap, high-volume
    synth_model: str = "accounts/fireworks/models/deepseek-v4-pro"     # premium, one call

    # Optional — a GitHub token lifts the public API rate limit from 60 to 5000/hr.
    # Read-only / public scope is plenty. Leave blank to run unauthenticated.
    github_token: str = ""

    # Crawl politeness knobs.
    crawl_max_pages: int = 8
    crawl_concurrency: int = 5
    http_timeout: float = 15.0

    # Extraction knobs.
    extract_max_chars: int = 6000   # per-page text cap sent to the model
    extract_concurrency: int = 4    # parallel extraction calls

    # Synthesis: cap facts sent to the verdict prompt (all facts still render in the
    # memo) so a fact-rich company can't overflow the model and return no verdict.
    synth_max_facts: int = 40


settings = Settings()
