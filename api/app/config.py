"""Runtime configuration. Reads environment variables (compose: env_file .env)."""
from pathlib import Path
from typing import Optional

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
    gemini_model: str = "gemini-2.5-flash"
    groq_whisper_model: str = "whisper-large-v3"
    groq_llm_model: str = "llama-3.3-70b-versatile"


settings = Settings()
