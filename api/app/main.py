"""FastAPI entrypoint — the single endpoint n8n and the web form call."""
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import auth, daily_report, extraction, imagegen, jobs, logs, mailer, memory, prompt_loader, sheets
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
        auth.seed_admin()
        # Scheduler starts only with a reachable store: every job either reads
        # or records through it, so without one they would fail every tick and
        # fill the panel with noise no operator can act on.
        if jobs.start():
            print("[jobs] scheduler running")
    except logs.LogStoreError as exc:
        print(f"[logs] DISABLED — {exc}")
        print("[jobs] DISABLED — no log store")
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
        # Chains and prompt sizes are here so an operator can confirm what the
        # running process actually loaded, without shelling into the container.
        "chains": {
            "text": settings.extraction_text_chain,
            "image": settings.extraction_image_chain,
            "image_generation": settings.image_generation_chain,
        },
        "prompts": prompt_loader.available(),
    }


# ── Dashboard accounts ─────────────────────────────────────────────────────
# The gate is here rather than on the login form: the dashboard is a static
# bundle, and anyone who can open it can call these URLs directly from devtools.


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def login(payload: LoginIn, response: Response) -> dict:
    try:
        result = auth.login(payload.email, payload.password)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if result is None:
        # One message for every failure mode. Distinguishing "no such account"
        # from "wrong password" tells an attacker which emails are real.
        raise HTTPException(401, "identifiants invalides")
    auth.set_cookie(response, result["token"])
    auth.record(result["user"], "login")
    return {"user": result["user"]}


@app.post("/auth/logout")
def logout(
    response: Response,
    session: Optional[str] = Cookie(default=None, alias=auth.COOKIE_NAME),
    caller: Optional[dict] = Depends(auth.current_user),
) -> dict:
    auth.record(caller, "logout")
    auth.logout(session)
    auth.clear_cookie(response)
    return {"ok": True}


@app.get("/auth/me")
def whoami(caller: Optional[dict] = Depends(auth.current_user)) -> dict:
    """Who the browser is, or null. Deliberately not 401: the dashboard calls
    this on load to decide whether to show the login screen, and an error there
    would be indistinguishable from the API being down."""
    return {"user": caller}


class UserIn(BaseModel):
    email: str
    name: str
    password: str
    role: str = "chef"


@app.get("/users")
def list_users(caller: dict = Depends(auth.require_human)) -> dict:
    """Every account for the director; only their own for a chef."""
    try:
        users = auth.list_users()
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if caller.get("role") != "directeur":
        users = [u for u in users if u["id"] == caller["id"]]
    return {"users": users}


@app.post("/users")
def add_user(payload: UserIn, caller: dict = Depends(auth.require_director)) -> dict:
    try:
        user = auth.create_user(payload.email, payload.name, payload.password, payload.role)
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "user_created", target=user["email"], after=user["role"])
    return user


@app.delete("/users/{user_id}")
def remove_user(user_id: int, caller: dict = Depends(auth.require_director)) -> dict:
    if user_id == caller["id"]:
        # Deleting yourself locks everyone out if you are the only director, and
        # the seed only runs when the table is empty.
        raise HTTPException(422, "on ne peut pas supprimer son propre compte")
    try:
        deleted = auth.delete_user(user_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "user_deleted", target=str(user_id))
    return {"deleted": deleted}


@app.get("/history")
def user_history(
    user_id: Optional[int] = None, limit: int = 100, caller: dict = Depends(auth.require_human)
) -> dict:
    """A chef may only read their own history, whatever they ask for."""
    target = user_id if caller.get("role") == "directeur" else caller["id"]
    try:
        return auth.history(target, limit)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class VisitIn(BaseModel):
    route: str
    seconds: int


@app.post("/page-visit")
def track_visit(payload: VisitIn, caller: dict = Depends(auth.require_human)) -> dict:
    """Time spent on a page. Measured in the browser because the server cannot
    see how long a page stayed open, and sent with sendBeacon so it survives the
    tab closing."""
    auth.record_visit(caller.get("id"), payload.route, payload.seconds)
    return {"ok": True}


@app.post("/process", response_model=ProcessResponse)
async def process(
    audio: Optional[UploadFile] = File(None, description="Voice note (ogg/opus from WhatsApp)"),
    image: Optional[UploadFile] = File(None, description="Photo: notebook page, whiteboard, delivery note, or the work itself"),
    text: Optional[str] = Form(None, description="Raw report text (web form mode)"),
    provider: Optional[str] = Form(None, description="STT engine override (benchmark use)"),
    correlation_id: Optional[str] = Form(None, description="Trace id minted by n8n at reception"),
    channel: Optional[str] = Form(None, description="telegram | whatsapp | form"),
    technicien: Optional[str] = Form(None, description="Sender name, for log filtering"),
) -> ProcessResponse:
    # Same trace id n8n threads through every stage, so the API's own errors
    # line up with the workflow's rows in the dashboard timeline.
    ctx = {"correlation_id": correlation_id, "channel": channel, "technicien": technicien}
    # Nightly summary of this technician (app/memory.py), injected as context.
    # Best effort on purpose: an unknown sender or a log store outage must
    # degrade to plain extraction, not fail a report someone is waiting for.
    try:
        sender_profile = logs.profile_for(technicien)
    except logs.LogStoreError:
        sender_profile = None

    provided = [name for name, value in (("audio", audio), ("image", image), ("text", text)) if value is not None]
    if len(provided) != 1:
        detail = f"Provide exactly one of 'audio', 'image' or 'text' (got: {provided or 'none'})"
        await _log("api", "error", message=detail, **ctx)
        raise HTTPException(422, detail)

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
    elif image is not None:
        # The vision path skips the text step entirely: the model reads the
        # photo and fills the schema in one call, so there is no intermediate
        # transcription to store or to get wrong twice.
        blob = await image.read()
        if not blob:
            raise HTTPException(422, "Empty image file")
        t1 = time.time()
        try:
            report, model_used = await run_in_threadpool(
                extraction.extract_report_from_image, blob,
                image.content_type or "image/jpeg", sender_profile,
            )
        except extraction.ExtractionError as exc:
            await _log(
                "extracted", "error", message=f"image extraction failed: {exc}",
                duration_ms=int((time.time() - t1) * 1000), **ctx,
            )
            raise HTTPException(502, f"image extraction failed: {exc}") from exc

        # There is no raw text for a photo. The model's own summary is the most
        # faithful thing to put in the column, marked so nobody reads it as a
        # verbatim quote from the technician.
        rapport_complet = f"[photo] {report.resume}"
        warnings.append("image_input")
        await _log(
            "extracted", "info", message="ok (image)",
            duration_ms=int((time.time() - t1) * 1000),
            payload={"model": model_used, "chantier": report.chantier, "bytes": len(blob)}, **ctx,
        )
        return ProcessResponse(
            rapport_complet=rapport_complet, report=report, transcription=None, warnings=warnings,
        )
    else:
        rapport_complet = (text or "").strip()
        if not rapport_complet:
            await _log("api", "error", message="Empty text", **ctx)
            raise HTTPException(422, "Empty text")

    t1 = time.time()
    try:
        report, model_used = await run_in_threadpool(
            extraction.extract_report_with_model, rapport_complet, sender_profile
        )
    except extraction.ExtractionError as exc:
        await _log(
            "extracted", "error", message=f"extraction failed: {exc}",
            duration_ms=int((time.time() - t1) * 1000), **ctx,
        )
        raise HTTPException(502, f"extraction failed: {exc}") from exc

    await _log(
        "extracted", "info", message="ok",
        duration_ms=int((time.time() - t1) * 1000),
        payload={"model": model_used, "chantier": report.chantier}, **ctx,
    )

    return ProcessResponse(
        rapport_complet=rapport_complet,
        report=report,
        transcription=transcription,
        warnings=warnings,
    )


# No auth: dashboard + API run only on the admin's machine (localhost), decided 2026-07-23.
@app.get("/reports")
def list_reports(caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"reports": sheets.read_reports()}
    except sheets.SheetsError as exc:
        raise HTTPException(502, f"sheets read failed: {exc}") from exc


class ReportPatch(BaseModel):
    field: str
    value: Optional[str] = None


@app.patch("/reports/{row}")
def patch_report(row: int, payload: ReportPatch, caller: dict = Depends(auth.require_human)) -> dict:
    if row < 2:
        raise HTTPException(422, "row must be >= 2 (row 1 is the header)")

    # Read the old value before overwriting it, so the history can say
    # "goulottes_m: 40 → 45" instead of "someone edited a row". Costs one extra
    # Sheets read per edit; there is no other moment when the previous value
    # still exists.
    previous = None
    try:
        current = next((r for r in sheets.read_reports() if r.get("_row") == row), None)
        previous = (current or {}).get(payload.field)
    except sheets.SheetsError:
        pass  # an unreadable Sheet must not block the correction itself

    try:
        sheets.update_report_field(row, payload.field, payload.value)
    except sheets.SheetsError as exc:
        detail = str(exc)
        raise HTTPException(422 if "unknown column" in detail else 502, detail) from exc

    # Clearing flag_review is "handling a flagged report" — the count the
    # director asked for — so it is recorded as its own action rather than as
    # one more field edit lost among the others.
    handled = payload.field == "flag_review" and (payload.value or "").upper() not in ("TRUE", "1")
    auth.record(
        caller,
        "flag_cleared" if handled else "report_edited",
        target=f"row {row} · {payload.field}",
        before=previous,
        after=payload.value,
    )
    return {"ok": True}


class DailyReportRequest(BaseModel):
    """Payload built by the n8n end-of-day cron from today's Sheet rows."""

    date: str = Field(..., description="Date du jour (ex: 2026-07-23)")
    rows: List[dict] = Field(..., description="Lignes du Sheet pour la date donnée")


@app.post("/daily-report", response_model=daily_report.DailyReportContent)
def daily_report_endpoint(payload: DailyReportRequest, caller: dict = Depends(auth.require_user)) -> daily_report.DailyReportContent:
    auth.record(caller, "report_generated", target=payload.date)
    if not payload.rows:
        raise HTTPException(422, "No rows for the given date")
    try:
        return daily_report.generate_daily_report(payload.date, payload.rows)
    except daily_report.DailyReportError as exc:
        raise HTTPException(502, f"daily report failed: {exc}") from exc


class ImageCardRequest(BaseModel):
    """Rows already extracted, plus what to call the card."""

    title: str = Field(..., description="Titre affiché sur la carte (ex: 'Semaine 30')")
    rows: List[dict] = Field(..., description="Lignes du Sheet pour la période")
    extra: Optional[str] = Field(None, description="Consigne libre de l'utilisateur")


@app.post("/generate-image")
async def generate_image(payload: ImageCardRequest, caller: dict = Depends(auth.require_human)) -> dict:
    auth.record(caller, "image_generated", target=getattr(payload, 'date', None))
    """Illustrated summary card for a day or week.

    Returns the image as a base64 data URI rather than a file: the dashboard
    only ever displays it, and this is generated content that must never be
    written to the Sheet or confused with a technician's own photo.

    Only fired by an explicit click — image models burn free-tier quota much
    faster than the text ones.
    """
    if not payload.rows:
        raise HTTPException(422, "No rows to illustrate")
    try:
        data, mime, model = await run_in_threadpool(
            imagegen.generate_card, payload.rows, payload.title, payload.extra
        )
    except imagegen.ImageGenerationError as exc:
        await _log("image_generated", "error", message=f"image generation failed: {exc}")
        raise HTTPException(502, f"image generation failed: {exc}") from exc

    await _log("image_generated", "info", message="ok", payload={"model": model, "bytes": len(data)})
    import base64

    return {
        "model": model,
        "mime_type": mime,
        "data_uri": f"data:{mime};base64,{base64.b64encode(data).decode()}",
    }


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
def create_log(event: LogEvent, caller: dict = Depends(auth.require_user)) -> dict:
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
def prune_logs(days: int = logs.RETENTION_DAYS, caller: dict = Depends(auth.require_director)) -> dict:
    """Retention sweep, called by the daily cron workflow."""
    try:
        return {"deleted": logs.prune(days)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ClaimRequest(BaseModel):
    message_id: str
    channel: Optional[str] = None


@app.post("/logs/claim")
def claim(payload: ClaimRequest, caller: dict = Depends(auth.require_user)) -> dict:
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
def queue_write(item: FailedWrite, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        return {"id": logs.queue_failed_write(item.payload, item.error, item.correlation_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/sheet-queue")
def list_queue(limit: int = 20, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        return {"pending": logs.pending_writes(limit)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


# ── Scheduled jobs ─────────────────────────────────────────────────────────
# The three cron bands that used to live in n8n. The scheduler runs them; these
# two routes are how the dashboard sees and forces them.


@app.get("/jobs")
def list_jobs(caller: dict = Depends(auth.require_human)) -> dict:
    return {"jobs": jobs.status()}


@app.post("/jobs/{name}/run")
async def run_job(name: str, caller: dict = Depends(auth.require_human)) -> dict:
    """Run one job now. Never 500s on a job failure — the outcome is the payload.

    Off the event loop: these read the Sheet and call models, and a synchronous
    handler would freeze every other request for the duration.
    """
    if name not in jobs.JOBS:
        raise HTTPException(404, f"unknown job: {name}")
    auth.record(caller, "job_run", target=name)
    return await run_in_threadpool(jobs.run, name)


# ── Technician directory ───────────────────────────────────────────────────
# Managed from the dashboard, read by the reception workflow to authorize a
# sender before any transcription happens.


class TechnicianIn(BaseModel):
    channel: str = Field(..., description="telegram | whatsapp")
    external_id: str = Field(..., description="Telegram chat id or WhatsApp number")
    name: str
    role: Optional[str] = None
    active: bool = True


@app.get("/technicians")
def list_technicians(caller: dict = Depends(auth.require_human)) -> dict:
    """People, each with their channel identities and remembered facts.

    Still `/technicians` and still keyed `technicians`: the dashboard and the
    workflow both call it, and renaming a working endpoint to match an internal
    refactor buys nothing an operator can see.
    """
    try:
        return {"technicians": logs.list_persons()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/technicians")
def add_technician(payload: TechnicianIn, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        created = logs.upsert_technician(
            payload.channel, payload.external_id, payload.name, payload.role, payload.active
        )
        auth.record(caller, "technician_added", target=f"{payload.channel} {payload.external_id}",
                    after=payload.name)
        return created
    except logs.LogStoreError as exc:
        detail = str(exc)
        # Bad channel or blank field is the caller's mistake (422); anything
        # else is the store being unreachable (502).
        raise HTTPException(422 if "unknown channel" in detail or "required" in detail else 502, detail) from exc


@app.delete("/technicians/{tech_id}")
def remove_technician(tech_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        auth.record(caller, "technician_removed", target=str(tech_id))
        return {"deleted": logs.delete_technician(tech_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/persons/{person_id}")
def remove_person(person_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    """Delete a person, their identities and their memory."""
    try:
        auth.record(caller, "person_removed", target=str(person_id))
        return {"deleted": logs.delete_person(person_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/persons/{person_id}/profile")
def refresh_one_profile(person_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    """Regenerate a single profile. The dashboard's button, and the way to fix a
    wrong profile without waiting for the next cron."""
    try:
        person = next((p for p in logs.list_persons() if p["id"] == person_id), None)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if person is None:
        raise HTTPException(404, f"person {person_id} not found")
    auth.record(caller, "profile_refreshed", target=person["name"])
    return memory.refresh_person(person, sheets.read_reports())


@app.post("/profiles/refresh")
def refresh_all_profiles(caller: dict = Depends(auth.require_user)) -> dict:
    """Rebuild every profile. Called by the 03:00 cron in n8n.

    The Sheet is read once for all of them: it is the slow part, and reading it
    per technician would turn a nightly job into a quota problem of its own.
    """
    try:
        persons = logs.list_persons()
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    rows = sheets.read_reports()
    results = [memory.refresh_person(p, rows) for p in persons]
    return {"refreshed": sum(1 for r in results if r["updated"]), "results": results}


@app.get("/technicians/lookup")
def lookup_technician(channel: str, external_id: str, caller: dict = Depends(auth.require_user)) -> dict:
    """Authorization check for n8n: returns the technician or `found: false`."""
    try:
        found = logs.find_technician(channel, external_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"found": found is not None, "technician": found}


# ── Operator settings ──────────────────────────────────────────────────────
# Report schedule, notification recipients and export format. Stored here so
# the dashboard and any scheduler read one source of truth.


class SettingsIn(BaseModel):
    values: Dict[str, Any]


@app.get("/settings")
def read_settings(caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"settings": logs.get_settings()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put("/settings")
def write_settings(payload: SettingsIn, caller: dict = Depends(auth.require_human)) -> dict:
    auth.record(caller, "settings_saved", detail=payload.values)
    try:
        return {"settings": logs.put_settings(payload.values)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class TestMailIn(BaseModel):
    to: str


@app.post("/notify/test")
def send_test_mail(payload: TestMailIn, caller: dict = Depends(auth.require_human)) -> dict:
    auth.record(caller, "test_mail_sent", target=payload.to)
    """Send one plain-text probe so an address can be verified before it matters.

    Credentials are optional at startup, so an unconfigured install gets a 422
    naming exactly which variables are missing instead of a silent no-op.
    """
    if not settings.smtp_user or not settings.smtp_password:
        raise HTTPException(422, str(mailer.MailError(
            "SMTP is not configured — set SMTP_USER and SMTP_PASSWORD in .env "
            "(Gmail requires an app password, not the account password)"
        )))
    try:
        mailer.send(
            [payload.to],
            "aznet — test de notification",
            "Ceci est un message de test envoyé depuis le tableau de bord aznet.\n"
            "Si vous le recevez, l'adresse est correctement configurée pour les "
            "rapports quotidiens et hebdomadaires.",
        )
    except mailer.MailError as exc:
        # 502: the mail relay refused us, which is not the caller's mistake.
        raise HTTPException(502, str(exc)) from exc

    return {"sent": True, "to": payload.to}


# ── Service uptime samples ─────────────────────────────────────────────────


class SampleIn(BaseModel):
    service: str
    state: str


class SamplesIn(BaseModel):
    samples: List[SampleIn]


@app.post("/service-samples")
def post_samples(payload: SamplesIn) -> dict:
    try:
        return {"written": logs.record_samples([s.model_dump() for s in payload.samples])}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/service-samples")
def get_samples(hours: int = 1) -> dict:
    try:
        return {"samples": logs.read_samples(hours)}
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
