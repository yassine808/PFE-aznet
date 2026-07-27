"""Runtime configuration. Reads environment variables (compose: env_file .env)."""
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (shared with docker-compose); anchor to this file
# so the service finds it regardless of the process working directory.
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(_ROOT_ENV, ".env"), extra="ignore")

    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    hf_token: Optional[str] = None

    # default engine until the week-1 benchmark decides (PLAN.md sprint 1)
    stt_provider: str = "groq"

    # pipeline log store (app/logs.py). Read here rather than via os.getenv so the
    # host-run uvicorn sees .env too — Docker's env_file only populates the real
    # environment for the containerised api service.
    database_url: Optional[str] = None

    # dashboard backend (Sheets read/write; no auth — runs on the admin's PC only)
    sheet_id: Optional[str] = None
    google_service_account_json: str = "./credentials/service-account.json"
    # rolling alias, lite pool — pinned "gemini-2.5-flash" got retired (404, Jul 2026)
    # and the flagship "gemini-flash-latest" pool 503s under free-tier evening load;
    # lite is verified live and plenty for structured extraction (benchmark revisits)
    gemini_model: str = "gemini-flash-lite-latest"
    groq_whisper_model: str = "whisper-large-v3"
    groq_llm_model: str = "llama-3.3-70b-versatile"

    # Ordered "provider:model" fallback chains, one per input shape. Tried left
    # to right; the first success wins (app/extraction.py). Ranked by
    # benchmark/run_model_benchmark.py — see benchmark/README.md for the table.
    #
    # Text mixes vendors on purpose: Gemini and Groq have separate free-tier
    # quotas, so a Gemini rate limit falls through to a different company's
    # capacity rather than to another queue behind the same meter.
    #
    # Image is Google-only because the free Groq catalogue has no vision model
    # (verified against GET /models), so the fallbacks buy resilience against a
    # single model 404ing or overloading, not against Google being down.
    extraction_text_chain: str = (
        "gemini:gemini-3.6-flash,groq:openai/gpt-oss-120b,gemini:gemini-flash-lite-latest"
    )
    extraction_image_chain: str = (
        "gemini:gemini-3.6-flash,gemini:gemini-2.5-flash,gemini:gemini-flash-lite-latest"
    )

    # Notification mail, used by POST /notify/test so the dashboard can prove a
    # recipient address before the end-of-day report goes out. Optional at
    # startup like every other key: the endpoint fails loudly with a precise
    # message when they are unset rather than the API refusing to boot.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    # The repo .env spells this SMTP_PASS while the field name implies
    # SMTP_PASSWORD; accept both rather than have the Test button 422 with
    # "SMTP is not configured" against a file that plainly configures it.
    smtp_password: Optional[str] = Field(None, validation_alias=AliasChoices("SMTP_PASSWORD", "SMTP_PASS"))
    smtp_from: Optional[str] = None


settings = Settings()
