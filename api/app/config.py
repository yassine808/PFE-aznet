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
    # HF_TOKEN is NOT read here any more. It only ever served hf_darija, deleted
    # 2026-08-08, and it is a download credential — benchmark/download_models.py
    # needs it to fetch gated weights, nothing at runtime does.

    # Ordered STT fallback chain: tried left to right, first success wins, all
    # failing raises one combined error (main.py:_transcribe_engine). A Groq
    # outage must fall through instead of costing the technician their report.
    #
    # This is the DEFAULT only. The live order is stored in app_settings and
    # edited by the director from the dashboard, so changing it needs no restart
    # (logs.get_settings -> "stt_chain").
    #
    # Order is ACCURACY, judged by a native Darija speaker against the audio
    # (2026-08-08), not latency: gemini first, then the local Darija fine-tune,
    # then groq. The chain is first-success-wins, so position 1 serves
    # essentially every note — gemini's 4.8 s is the deliberate price of its
    # accuracy over groq's 1.9 s. groq sits last as the fast, always-available
    # floor. Measurements: benchmark/STT-BENCHMARK-STATUS.md.
    stt_chain: str = "gemini,local,groq"
    # GPU sidecar running BounharAbdelaziz/Morocco-Darija-STT-large
    # (benchmark/stt_server.py). Unset means the `local` engine is unavailable
    # and the chain simply skips it — never a silent fallback to nothing.
    stt_local_url: Optional[str] = None

    # pipeline log store (app/logs.py). Read here rather than via os.getenv so the
    # host-run uvicorn sees .env too — Docker's env_file only populates the real
    # environment for the containerised api service.
    database_url: Optional[str] = None

    # dashboard backend (Sheets read/write; every route is auth-gated in main.py)
    sheet_id: Optional[str] = None
    google_service_account_json: str = "./credentials/service-account.json"
    # Optional parent folder for the durable audio archive (app/drive.py). Unset
    # = files land in the service account's Drive root.
    google_drive_folder_id: Optional[str] = None
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
    # Re-ranked 2026-08-15 over the twenty cases in text_cases.json — the file
    # was rewritten that day for the current schema, so the July ranking below
    # was measured against a contract that no longer exists:
    #   gemini-3.5-flash-lite     100% couverture, 0 inventés, 99%,  2.3s
    #   gemini-flash-lite-latest  100% couverture, 0 inventés, 99%,  2.3s
    #   gemini-3.1-flash-lite     100% couverture, 0 inventés, 96%,  1.8s
    #   openai/gpt-oss-120b        85% couverture, 2 inventés, 94%, 30.4s
    #   gemini-3.6-flash           80% couverture, 0 inventés, 99%,  8.7s
    #
    # Ranked on coverage, then hallucinations, then accuracy, then latency.
    # (July, for comparison, put gpt-oss-120b first on 100%/0 invented/1.6s
    # over ten cases. It is the same criterion on a harder corpus: the article
    # and blocker cases are new, and it is the only text model that invented
    # anything at all this time.)
    #
    # Why not simply "the three fastest": the second entry is Groq **on
    # purpose**. Gemini and Groq meter their free tiers separately, so an
    # all-Google chain has one meter and three names on it — the fallback buys
    # nothing at the exact moment it is needed. Vendor alternation is the point
    # of the second slot, and gpt-oss-120b keeps it despite ranking fourth.
    #
    # Why the pinned name first and the `-latest` alias last, when they scored
    # identically: an alias silently becomes a different model. A benchmark
    # result is about the model it measured, so the evidence pins the primary,
    # and the floating name sits where a surprise costs the least.
    extraction_text_chain: str = (
        "gemini:gemini-3.5-flash-lite,groq:openai/gpt-oss-120b,gemini:gemini-flash-lite-latest"
    )
    # Not gemini-2.5-flash: it is still in the model list but 404s with "no
    # longer available to new users" (benchmark run 2026-07-27). Nor
    # gemini-3.5-flash, which answered 503 "high demand" on 10/10 calls.

    # Nightly technician profiles (app/memory.py). Prose, not JSON, and nobody is
    # waiting on it -- so the cheap/fast text models come first and a slow one is
    # a fine fallback at 03:00.
    profile_chain: str = (
        "groq:openai/gpt-oss-120b,gemini:gemini-flash-lite-latest,gemini:gemini-3.6-flash"
    )

    # Re-ranked 2026-08-15 against the plan photos in dataset/plan_cases.json —
    # the first real image data this project has had. Criterion fixed before
    # the run, as for STT: localization accuracy (does it name the marked
    # zones) and hallucination (does it claim zones nobody marked).
    #   gemini-3.5-flash-lite     92% rappel, 0 hallucinations,  1.3s
    #   gemini-flash-lite-latest  92% rappel, 0 hallucinations,  1.4s
    #   gemini-3.6-flash          92% rappel, 1 hallucination,  13.4s
    #   gemini-3.1-flash-lite    100% rappel, 4 hallucinations,  1.5s  <- NOT used
    #
    # 3.1-flash-lite is the reason recall alone must not pick the model: it
    # tops recall by naming rooms nobody marked, which is how an invented floor
    # reaches `etages`. It is excluded, not merely ranked last — on the image
    # path there is no transcription behind the answer to contradict it.
    #
    # Google-only, and that is a real fragility rather than a preference: the
    # free Groq catalogue has no multimodal model (re-verified 2026-08-15 by
    # enumerating it — 15 models, none vision — and by Llama 4 Scout/Maverick
    # answering 404). So these three names share one meter, and the fallbacks
    # buy resilience against a single model overloading, never against Google
    # being unavailable. On the evening of 2026-08-15 gemini-3.7-flash answered
    # 503 "high demand" on 13 of 20 calls, which is exactly what taking out the
    # whole image path would look like.
    extraction_image_chain: str = (
        "gemini:gemini-3.5-flash-lite,gemini:gemini-flash-lite-latest,gemini:gemini-3.6-flash"
    )

    # Dashboard auth. Both optional so the API still boots on a machine that has
    # neither -- the endpoints fail loudly at call time instead, same as the
    # model keys.
    #
    # `internal_api_key` is what n8n sends as X-API-Key. Unset means machine
    # access is DISABLED, never "everyone is a machine".
    internal_api_key: Optional[str] = None
    # First-account seeding (auth.seed_admin). Read through Settings so the
    # host-run `uvicorn --reload` dev flow (which loads .env via pydantic-settings)
    # sees them too, not just the containerised env_file path — before this, an
    # .env with ADMIN_EMAIL/ADMIN_PASSWORD only took effect inside Docker and the
    # reload process kept seeding a throwaway "admin" account nobody asked for.
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    admin_name: str = "Directeur"
    # Off on http://localhost, which is where this runs today: a Secure cookie is
    # simply not sent over http, so leaving it on would make login silently fail.
    # Flip to true the day the dashboard is published over HTTPS.
    cookie_secure: bool = False

    # n8n's public API, read by the dashboard's orchestrator panels through
    # GET /n8n/workflows and /n8n/executions. The key lives here rather than in
    # the reverse proxy: a proxy that injects it would hand an unauthenticated
    # n8n admin API to anyone who can reach the public URL, whereas these routes
    # sit behind require_human like the rest of the dashboard.
    n8n_url: str = "http://n8n:5678"  # NOSONAR — internal docker-compose service name, not internet-reachable
    n8n_api_key: Optional[str] = None

    # Where the dashboard answers, used to build the "open the report" link in
    # outgoing mail. It has to be an address the *recipient's* browser can
    # reach, which is why it is not derived from the request: the scheduler
    # sends these from a background thread with no request to derive from, and
    # a link to `http://api:8000` would work only inside the compose network.
    # Set it to the Tailscale Funnel hostname once the dashboard is published.
    dashboard_url: str = "http://localhost:8080"

    # How many trusted proxies sit in front of this API, used to pick the real
    # client address out of X-Forwarded-For when throttling logins (main.py).
    # 1 = nginx alone; 2 = Tailscale Funnel in front of nginx; 0 = no proxy,
    # host-run uvicorn. Wrong value either lets a script bypass the throttle or
    # collapses every visitor onto one key.
    trusted_proxy_hops: int = 1

    # Comma-separated browser origins allowed to call this API cross-origin. The
    # served dashboard is same-origin and needs no entry here; the default covers
    # the Vite dev server only. Deliberately not "*" -- see main.py.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

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
    smtp_password: Optional[str] = Field(default=None, validation_alias=AliasChoices("SMTP_PASSWORD", "SMTP_PASS"))
    smtp_from: Optional[str] = None

    # Outbound technician replies (POST /reply — the inbox's composer).
    # n8n holds the credentials for reception; the API sends replies itself so
    # the dashboard keeps working even while n8n is down. Same values as n8n's
    # channel credentials: the Telegram bot token, and the WhatsApp System User
    # token + the WABA phone number id. Optional: unset makes /reply answer 501
    # with a precise message instead of the API refusing to boot.
    telegram_bot_token: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None


settings = Settings()
