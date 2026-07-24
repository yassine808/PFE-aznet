"""FastAPI entrypoint — the single endpoint n8n and the web form call."""
import time
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import daily_report, extraction, sheets
from app.config import settings
from app.providers import available_providers, get_provider
from app.providers.base import TranscriptionError
from app.schemas import ProcessResponse

app = FastAPI(
    title="AI Rapport Journalier — aznet",
    description="Voice/text daily report → structured JSON (PFE 2026)",
    version="0.1.0",
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
) -> ProcessResponse:
    if (audio is None) == (text is None):
        raise HTTPException(422, "Provide exactly one of 'audio' or 'text'")

    warnings: List[str] = []
    transcription = None

    if audio is not None:
        blob = await audio.read()
        if not blob:
            raise HTTPException(422, "Empty audio file")
        engine = provider or settings.stt_provider
        try:
            transcription = get_provider(engine).transcribe(
                blob, audio.content_type or "audio/ogg"
            )
        except ValueError as exc:  # unknown provider name
            raise HTTPException(422, str(exc)) from exc
        except TranscriptionError as exc:
            raise HTTPException(502, f"transcription failed: {exc}") from exc
        rapport_complet = transcription.text
        if len(rapport_complet) < MIN_USABLE_CHARS:
            warnings.append("short_transcription")
        if transcription.confidence is not None and transcription.confidence < LOW_CONFIDENCE_THRESHOLD:
            warnings.append("low_confidence_transcription")
    else:
        rapport_complet = (text or "").strip()
        if not rapport_complet:
            raise HTTPException(422, "Empty text")

    try:
        report = extraction.extract_report(rapport_complet)
    except extraction.ExtractionError as exc:
        raise HTTPException(502, f"extraction failed: {exc}") from exc

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
