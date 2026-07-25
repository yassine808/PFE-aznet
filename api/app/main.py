"""FastAPI entrypoint — the single endpoint n8n and the web form call."""
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import daily_report, extraction, logs, sheets
from app.config import settings
from app.providers import available_providers, get_provider
from app.providers.base import TranscriptionError
from app.schemas import ProcessResponse

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the log tables if the DB is reachable.

    Deliberately non-fatal: the pipeline's job is transcribing voice notes, and
    that must not stop because the observability store is down. The failure is
    printed loudly rather than swallowed silently.
    """
    try:
        logs.init_schema()
        print("[logs] postgres schema ready")
    except logs.LogStoreError as exc:
        print(f"[logs] DISABLED — {exc}")
    yield


app = FastAPI(
    title="AI Rapport Journalier — aznet",
    description="Voice/text daily report → structured JSON (PFE 2026)",
    version="0.1.0",
    lifespan=lifespan,
)

# Dashboard SPA calls from another origin (Vite dev :5173 / Vercel); Sheets creds stay server-side
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_USABLE_CHARS = 10
LOW_CONFIDENCE_THRESHOLD = 0.5  # below this, flag for manual review in the dashboard

# Wall-clock start of this process — the dashboard reads uptime from /health to
# show an "API online / uptime" status tile (ops visibility on the admin PC).
_STARTED_AT = time.time()


async def _log(stage: str, level: str = "info", **kwargs) -> None:
    """Best-effort event log from an async handler.

    psycopg2 is synchronous: calling it directly from `async def process()`
    would block the event loop for the whole round-trip, stalling every other
    concurrent request. run_in_threadpool keeps the loop free.
    """
    await run_in_threadpool(logs.write_safe, stage, level, **kwargs)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "started_at": _STARTED_AT,
        "stt_providers": available_providers(),
        "stt_default": settings.stt_provider,
    }


@app.post("/process", response_model=ProcessResponse)
async def process(
    audio: Optional[UploadFile] = File(None, description="Voice note (ogg/opus from WhatsApp)"),
    text: Optional[str] = Form(None, description="Raw report text (web form mode)"),
    provider: Optional[str] = Form(None, description="STT engine override (benchmark use)"),
    correlation_id: Optional[str] = Form(None, description="Trace id minted by n8n at reception"),
    channel: Optional[str] = Form(None, description="telegram | whatsapp | form"),
    technicien: Optional[str] = Form(None, description="Sender name, for log filtering"),
) -> ProcessResponse:
    # Same trace id n8n threads through every stage, so the API's own errors
    # line up with the workflow's rows in the dashboard timeline.
    ctx = {"correlation_id": correlation_id, "channel": channel, "technicien": technicien}

    if (audio is None) == (text is None):
        await _log("api", "error", message="Provide exactly one of 'audio' or 'text'", **ctx)
        raise HTTPException(422, "Provide exactly one of 'audio' or 'text'")

    warnings: List[str] = []
    transcription = None

    if audio is not None:
        blob = await audio.read()
        if not blob:
            raise HTTPException(422, "Empty audio file")
        engine = provider or settings.stt_provider
        t0 = time.time()
        try:
            transcription = get_provider(engine).transcribe(
                blob, audio.content_type or "audio/ogg"
            )
        except ValueError as exc:  # unknown provider name
            await _log("api", "error", message=f"unknown provider: {exc}", **ctx)
            raise HTTPException(422, str(exc)) from exc
        except TranscriptionError as exc:
            await _log(
                "transcribed", "error", message=f"transcription failed: {exc}",
                duration_ms=int((time.time() - t0) * 1000),
                payload={"engine": engine}, **ctx,
            )
            raise HTTPException(502, f"transcription failed: {exc}") from exc
        rapport_complet = transcription.text
        if len(rapport_complet) < MIN_USABLE_CHARS:
            warnings.append("short_transcription")
        if transcription.confidence is not None and transcription.confidence < LOW_CONFIDENCE_THRESHOLD:
            warnings.append("low_confidence_transcription")
        await _log(
            "transcribed", "warn" if warnings else "info",
            message=", ".join(warnings) or "ok",
            duration_ms=int((time.time() - t0) * 1000),
            payload={"engine": engine, "chars": len(rapport_complet)}, **ctx,
        )
    else:
        rapport_complet = (text or "").strip()
        if not rapport_complet:
            await _log("api", "error", message="Empty text", **ctx)
            raise HTTPException(422, "Empty text")

    t1 = time.time()
    try:
        report = extraction.extract_report(rapport_complet)
    except extraction.ExtractionError as exc:
        await _log(
            "extracted", "error", message=f"extraction failed: {exc}",
            duration_ms=int((time.time() - t1) * 1000), **ctx,
        )
        raise HTTPException(502, f"extraction failed: {exc}") from exc

    await _log(
        "extracted", "info", message="ok",
        duration_ms=int((time.time() - t1) * 1000),
        payload={"chantier": report.chantier}, **ctx,
    )

    return ProcessResponse(
        rapport_complet=rapport_complet,
        report=report,
        transcription=transcription,
        warnings=warnings,
    )


# No auth: dashboard + API run only on the admin's machine (localhost), decided 2026-07-23.
@app.get("/reports")
def list_reports() -> dict:
    try:
        return {"reports": sheets.read_reports()}
    except sheets.SheetsError as exc:
        raise HTTPException(502, f"sheets read failed: {exc}") from exc


class ReportPatch(BaseModel):
    field: str
    value: Optional[str] = None


@app.patch("/reports/{row}")
def patch_report(row: int, payload: ReportPatch) -> dict:
    if row < 2:
        raise HTTPException(422, "row must be >= 2 (row 1 is the header)")
    try:
        sheets.update_report_field(row, payload.field, payload.value)
    except sheets.SheetsError as exc:
        detail = str(exc)
        raise HTTPException(422 if "unknown column" in detail else 502, detail) from exc
    return {"ok": True}


class DailyReportRequest(BaseModel):
    """Payload built by the n8n end-of-day cron from today's Sheet rows."""

    date: str = Field(..., description="Date du jour (ex: 2026-07-23)")
    rows: List[dict] = Field(..., description="Lignes du Sheet pour la date donnée")


@app.post("/daily-report", response_model=daily_report.DailyReportContent)
def daily_report_endpoint(payload: DailyReportRequest) -> daily_report.DailyReportContent:
    if not payload.rows:
        raise HTTPException(422, "No rows for the given date")
    try:
        return daily_report.generate_daily_report(payload.date, payload.rows)
    except daily_report.DailyReportError as exc:
        raise HTTPException(502, f"daily report failed: {exc}") from exc


# ── Pipeline logs (dashboard "Logs / n8n" panel) ────────────────────────────
# n8n POSTs one row per stage; the dashboard polls GET /logs every 5s.


class LogEvent(BaseModel):
    stage: str
    level: str = "info"
    message: Optional[str] = None
    correlation_id: Optional[str] = None
    channel: Optional[str] = None
    technicien: Optional[str] = None
    duration_ms: Optional[int] = None
    payload: Optional[dict] = None


@app.post("/logs")
def create_log(event: LogEvent) -> dict:
    try:
        log_id = logs.write(**event.model_dump())
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "id": log_id}


@app.get("/logs")
def list_logs(
    limit: int = 200,
    level: Optional[str] = None,
    channel: Optional[str] = None,
    stage: Optional[str] = None,
    correlation_id: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    try:
        return {
            "logs": logs.read(
                limit=limit, level=level, channel=channel,
                stage=stage, correlation_id=correlation_id, search=search,
            ),
            "stats": logs.stats(),
        }
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/logs")
def prune_logs(days: int = logs.RETENTION_DAYS) -> dict:
    """Retention sweep, called by the daily cron workflow."""
    try:
        return {"deleted": logs.prune(days)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ClaimRequest(BaseModel):
    message_id: str
    channel: Optional[str] = None


@app.post("/logs/claim")
def claim(payload: ClaimRequest) -> dict:
    """Idempotency gate. `fresh: false` means n8n must stop — already processed.

    Meta retries the WhatsApp webhook when it does not get a fast 200, which
    without this means duplicate Sheet rows, duplicate replies and duplicate
    free-tier quota burn.
    """
    try:
        fresh = logs.claim_message(payload.message_id, payload.channel)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"fresh": fresh}


# ── Sheet retry queue ──────────────────────────────────────────────────────
# Reply-first means the Sheet write is a recoverable side effect: failures park
# here and the cron workflow drains them, so no report is lost to a Google outage.


class FailedWrite(BaseModel):
    payload: dict
    error: str
    correlation_id: Optional[str] = None


@app.post("/sheet-queue")
def queue_write(item: FailedWrite) -> dict:
    try:
        return {"id": logs.queue_failed_write(item.payload, item.error, item.correlation_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/sheet-queue")
def list_queue(limit: int = 20) -> dict:
    try:
        return {"pending": logs.pending_writes(limit)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ResolveRequest(BaseModel):
    ok: bool
    error: Optional[str] = None


@app.patch("/sheet-queue/{write_id}")
def resolve_queue_item(write_id: int, payload: ResolveRequest) -> dict:
    try:
        logs.resolve_write(write_id, payload.ok, payload.error)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True}
