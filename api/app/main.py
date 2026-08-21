"""FastAPI entrypoint — the single endpoint n8n and the web form call."""
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, model_validator

from app import auth, daily_report, docx_report, drive, extraction, jobs, journal, logs, mailer, memory, prompt_loader, reply, sheets, stock, usage
from app.config import settings
from app.providers import available_providers, get_provider
from app.providers.base import TranscriptionError, TranscriptionInfo
from app.schemas import ProcessResponse

# What both channels send when they do not label the voice note themselves.
DEFAULT_AUDIO_MIME = "audio/ogg"
# 404 body for every /tasks route — one string, so the wording cannot drift.
TASK_NOT_FOUND = "tâche inconnue"

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

# In production the dashboard is served from the same origin as this API (nginx
# routes / to the build and /api here), so no browser request is cross-origin and
# this middleware never fires. It exists for `npm run dev` on :5173, which is a
# different origin. Hence a narrow default rather than "*": a wildcard on a
# publicly reachable API lets any page on the internet script it with the
# visitor's session, and allow_credentials cannot be combined with "*" anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_USABLE_CHARS = 10
LOW_CONFIDENCE_THRESHOLD = 0.5  # below this, flag for manual review in the dashboard

# Upload caps enforced *before* anything leaves this process: a 100 MB Telegram
# dump or a 30 MB "photo" must cost us nothing (no Sheet write, no quota burn),
# and a request that big is certainly a misdirected file, not a voice note.
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024

# Wall-clock start of this process — the dashboard reads uptime from /health to
# show an "API online / uptime" status tile (ops visibility on the admin PC).
_STARTED_AT = time.time()


async def _log(stage: str, level: str = "info", **kwargs) -> None:
    """Best-effort event log from an async handler.

    psycopg2 is synchronous: calling it directly from `async def process()`
    would block the event loop for the whole round-trip, stalling every other
    concurrent request. run_in_threadpool keeps the loop free.
    """
    # Underscore keys are carry-state for the request (e.g. _media_id), not log
    # fields: write_safe takes named columns and an extra kwarg would raise.
    await run_in_threadpool(logs.write_safe, stage, level,
                            **{k: v for k, v in kwargs.items() if not k.startswith("_")})


def _notify_report_event(
    technicien: Optional[str], rapport_complet: str, warnings: List[str], ctx: dict
) -> None:
    """The bell: a chef learns about their team's report, and about the flagged
    rows that need a human eye. Best-effort like every observability write — a
    log store outage must not cost the technician their summary.
    """
    try:
        # journal.REVIEW_WARNINGS, not a second copy of the same three strings:
        # it is what sets the row's `Flag review` cell, so a literal here means
        # the bell saying "à vérifier" and the Sheet column marking the row
        # could disagree the day either list is edited alone.
        if not (journal.REVIEW_WARNINGS & set(warnings)):
            logs.notify_technician_manager(
                technicien, "report",
                f"Nouveau rapport — {technicien or 'inconnu'}",
                (rapport_complet or "")[:300] or None, "#/reports",
            )
        else:
            logs.notify_technician_manager(
                technicien, "review",
                f"Rapport à vérifier — {technicien or 'inconnu'}",
                "Confiance faible ou entrée photo : à relire avant clôture.", "#/reports",
            )
    except logs.LogStoreError as exc:
        # Notifications cannot be awaited here (sync helper) — write_safe via
        # the regular log path, which is itself best-effort.
        logs.write_safe("api", "warn", message=f"notification failed: {exc}", **ctx)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "started_at": _STARTED_AT,
        "stt_providers": available_providers(),
        "stt_chain": _stt_chain(),
        # Chains and prompt sizes are here so an operator can confirm what the
        # running process actually loaded, without shelling into the container.
        "chains": {
            "text": settings.extraction_text_chain,
            "image": settings.extraction_image_chain,
        },
        "prompts": prompt_loader.available(),
    }


# ── Dashboard accounts ─────────────────────────────────────────────────────
# The gate is here rather than on the login form: the dashboard is a static
# bundle, and anyone who can open it can call these URLs directly from devtools.


class LoginIn(BaseModel):
    email: str
    password: str


# Generous enough that a person fumbling their password never notices, tight
# enough that guessing is pointless: 8 failures per 5 minutes per address.
LOGIN_MAX_FAILURES = 8
LOGIN_WINDOW_SECONDS = 300
_login_failures: Dict[str, List[float]] = {}


def _client_ip(request: Request) -> str:
    """The browser's address, as seen through the reverse proxy.

    `request.client.host` is nginx's container IP for every visitor once the
    dashboard is served same-origin, which would make the throttle below global:
    eight failures by anyone would lock out everyone.

    Which X-Forwarded-For entry is trustworthy depends on how many proxies sit in
    front, and the two deployments differ -- hence `trusted_proxy_hops` rather
    than a fixed rule:

      * nginx alone (aznet server, public 443): nginx sets
        `$proxy_add_x_forwarded_for`, i.e. "<caller's value>, <real peer>". The
        LAST entry is what nginx saw; the first is whatever the caller claimed.
        One hop.
      * Tailscale Funnel in front of nginx (the current setup): tailscaled
        *replaces* any caller-supplied header -- verified by sending
        "X-Forwarded-For: 9.9.9.9" and observing only tailscaled's value arrive
        -- then nginx appends its own peer. Two hops, so the first entry wins.

    Both wrong values fail, in opposite directions. Too LOW and the index lands
    on an entry one of our own proxies wrote -- the same address for every
    visitor -- so the whole team shares one key and eight failures by anyone
    locks everybody out. Too HIGH and it lands left of what the outermost proxy
    recorded, i.e. on a value the caller supplied, which a script rotates to
    dodge the limit entirely. Zero is handled above: no trusted proxy means no
    trustworthy entry, so the header is ignored rather than indexed.
    """
    forwarded = request.headers.get("x-forwarded-for")
    # Zero trusted proxies means the header is entirely caller-supplied, so it is
    # ignored rather than indexed: `len(hops) - 0` is one past the end, and the
    # `max(0, ...)` below only ever guarded the *upper* bound. Since the header
    # comes from the caller, that IndexError was a 500 on /auth/login that
    # anyone could trigger on a deployment configured the way config.py
    # documents for host-run uvicorn.
    if forwarded and settings.trusted_proxy_hops > 0:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            # Discard the entries our own proxies appended and keep the value the
            # outermost trusted one recorded. Everything left of that is supplied
            # by the caller and must never be trusted.
            return hops[max(0, len(hops) - settings.trusted_proxy_hops)]
    return request.client.host if request.client else "unknown"


def _login_allowed(client: str) -> bool:
    """Sliding-window throttle on failed logins, keyed by client address.

    bcrypt makes each attempt cost ~100 ms, which is a speed bump, not a limit:
    left alone, a script still gets tens of thousands of guesses a day against an
    account whose password a human chose. Only *failures* count, so a working
    session is never punished.

    ponytail: in-process dict, so it resets on restart and does not span
    replicas. Both are fine for one container on one server; move it to the
    `sessions` table's database if the API is ever scaled out.
    """
    now = time.time()
    hits = [t for t in _login_failures.get(client, []) if now - t < LOGIN_WINDOW_SECONDS]
    if hits:
        _login_failures[client] = hits
    else:
        # Drop the key rather than storing []: only a *successful* login popped
        # it before, so every address that ever mistyped a password kept a dict
        # entry for the life of the process.
        _login_failures.pop(client, None)
    return len(hits) < LOGIN_MAX_FAILURES


@app.post("/auth/login", responses={429: {"description": "Too many failed attempts"}, 502: {"description": "Log store unreachable"}, 401: {"description": "Invalid credentials"}})
def login(payload: LoginIn, response: Response, request: Request) -> dict:
    client = _client_ip(request)
    if not _login_allowed(client):
        # 429 rather than 401: the credentials were never checked, and saying so
        # tells an honest user locked out by a typo to simply wait.
        raise HTTPException(429, "trop de tentatives, réessayez dans quelques minutes")
    try:
        result = auth.login(payload.email, payload.password)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if result is None:
        _login_failures.setdefault(client, []).append(time.time())
        # One message for every failure mode. Distinguishing "no such account"
        # from "wrong password" tells an attacker which emails are real.
        raise HTTPException(401, "identifiants invalides")
    _login_failures.pop(client, None)
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


@app.get("/users", responses={502: {"description": "Log store unreachable"}})
def list_users(caller: dict = Depends(auth.require_human)) -> dict:
    """Every account for the director; only their own for a chef."""
    try:
        users = auth.list_users()
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if caller.get("role") != "directeur":
        users = [u for u in users if u["id"] == caller["id"]]
    return {"users": users}


@app.post("/users", responses={422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
def add_user(payload: UserIn, caller: dict = Depends(auth.require_director)) -> dict:
    # Only the .env-seeded account is ever "directeur" — every account created
    # here is a chef, regardless of what the client sends.
    try:
        user = auth.create_user(payload.email, payload.name, payload.password, "chef")
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "user_created", target=user["email"], after=user["role"])
    return user


@app.delete("/users/{user_id}", responses={422: {"description": "Cannot delete own account"}, 502: {"description": "Log store unreachable"}})
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


@app.get("/history", responses={502: {"description": "Log store unreachable"}})
def user_history(
    user_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    caller: dict = Depends(auth.require_human),
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


async def _transcribe_audio(audio: UploadFile, provider: Optional[str], ctx: dict,
                            message_id: Optional[str] = None):
    """Audio branch of /process: STT then a couple of quality warnings.

    Returns (transcription, rapport_complet, warnings, blob, media_id). Raises HTTPException
    on empty/oversized input, an unknown provider name, or a transcription failure.
    """
    blob = await audio.read(MAX_AUDIO_BYTES + 1)
    if not blob:
        raise HTTPException(422, "Empty audio file")
    if len(blob) > MAX_AUDIO_BYTES:
        raise HTTPException(422, f"Audio too large (max {MAX_AUDIO_BYTES // (1024 * 1024)} MB)")
    # Persist-first, since 2026-08-20. The archive used to happen *after* the
    # transcription that can fail, so a failed voice note left no blob anywhere —
    # and Telegram file paths (~1h) and Meta media URLs (minutes) both expire, so
    # there was nothing left to retry with. The retry queue is only possible
    # because the bytes are saved before anyone tries to read them.
    # Best-effort: a log-store outage must not cost a report that would otherwise
    # have been transcribed fine.
    media_id = None
    try:
        media_id = await run_in_threadpool(
            logs.save_media, ctx.get("channel"), None, message_id,
            "audio", audio.content_type, blob,
        )
    except logs.LogStoreError as exc:
        await _log("api", "warn", message=f"media archive failed: {exc}", **ctx)
    # Where _park reads it if the STT call below raises: the queued row must
    # point at the blob, and by then this frame is gone.
    ctx["_media_id"] = media_id
    t0 = time.time()
    try:
        # STT is pure synchronous I/O (requests/genai/groq/httpx) — run it off the
        # loop or one slow engine stalls every other concurrent request. The chain
        # lives in _transcribe_engine, which does the ordered fallback so a dead
        # engine never costs the technician their report.
        transcription = await run_in_threadpool(_transcribe_engine, blob, audio.content_type, provider)
    except ValueError as exc:  # unknown provider name
        await _log("api", "error", message=f"unknown provider: {exc}", **ctx)
        raise HTTPException(422, str(exc)) from exc
    except TranscriptionError as exc:
        await _log(
            "transcribed", "error", message=f"transcription failed: {exc}",
            duration_ms=int((time.time() - t0) * 1000),
            payload={"engine": provider or _stt_chain()}, **ctx,
        )
        raise HTTPException(502, f"transcription failed: {exc}") from exc

    engine = transcription.provider
    rapport_complet = transcription.text
    warnings: List[str] = []
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
    return transcription, rapport_complet, warnings, blob, media_id


def _stt_chain() -> str:
    """The live STT order.

    Stored in app_settings so the director can reorder the engines from the
    dashboard without a restart; `settings.stt_chain` from .env is the fallback
    for a fresh database or an unreachable log store. Read on every call rather
    than cached, for the same reason the scheduler re-reads its times: an edited
    order must take effect on the next voice note, not the next deploy.
    """
    try:
        stored = (logs.get_settings() or {}).get("stt_chain")
    except Exception:  # noqa: BLE001  # Postgres down must not stop transcription
        stored = None
    return stored if isinstance(stored, str) and stored.strip() else settings.stt_chain


def _transcribe_engine(
    blob: bytes, mime_type: Optional[str], forced: Optional[str]
) -> TranscriptionInfo:
    """Run the STT chain — synchronous, so callers wrap it in run_in_threadpool.

    `forced` is the benchmark override (`provider=` form field) and bypasses the
    chain exactly like the old single-engine path. The chain mirrors the
    extraction design in app/extraction.py: ordered engines, first success wins,
    every failure recorded, all of them failing raises one combined
    TranscriptionError — never a silent fallback to "no report".
    """
    if forced:
        # Unknown forced names must fail loudly (422 upstream): the benchmark
        # needs to learn a typo, not silently fall back to another engine.
        return get_provider(forced).transcribe(blob, mime_type or DEFAULT_AUDIO_MIME)
    failures: List[str] = []
    for name in (part.strip() for part in _stt_chain().split(",") if part.strip()):
        try:
            return get_provider(name).transcribe(blob, mime_type or DEFAULT_AUDIO_MIME)
        except (TranscriptionError, ValueError) as exc:
            # ValueError = unknown engine in the chain: a config typo must not
            # take the remaining engines down with it, just be recorded.
            failures.append(f"{name}: {exc}")
    raise TranscriptionError("no STT engine succeeded — " + " | ".join(failures))


async def _extract_from_image(
    image: UploadFile, sender_profile: Optional[str], caption: Optional[str],
    ctx: dict, message_id: Optional[str] = None,
) -> ProcessResponse:
    """Image branch of /process. The vision model reads the photo and fills the
    schema in one call, so there is no intermediate transcription to store or
    to get wrong twice — this returns the full ProcessResponse directly.
    """
    blob = await image.read(MAX_IMAGE_BYTES + 1)
    if not blob:
        raise HTTPException(422, "Empty image file")
    if len(blob) > MAX_IMAGE_BYTES:
        raise HTTPException(422, f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)")
    t1 = time.time()
    try:
        report, model_used = await run_in_threadpool(
            extraction.extract_report_from_image, blob,
            image.content_type or "image/jpeg", sender_profile, caption,
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
    warnings = ["image_input"]
    # Locations read off a photo get their own warning, and only when the model
    # actually returned some — a warning on every photo would be wallpaper.
    #
    # This one is measured, not assumed. The 2026-08-16 vision benchmark showed
    # attentional crowding under control: the same marks on the same corridor
    # are found when they are the only annotation on the plan, and missed by 3
    # models out of 4 once louder marks appear elsewhere in the same image. So
    # a zone list from a photo is plausibly SHORT, and a missing zone is
    # invisible downstream — it leaves no empty cell to notice, only a shorter
    # list. The row has to say so itself, or the reader trusts a partial answer.
    if any((report.etages, report.ailes, report.locaux_techniques)):
        warnings.append("photo_zones_partielles")
    if not report.has_data():
        warnings.append("no_report_content")
    await _log(
        "extracted", "info", message="ok (image)",
        duration_ms=int((time.time() - t1) * 1000),
        payload={"model": model_used, "etages": report.etages, "bytes": len(blob)}, **ctx,
    )
    # Archive the photo in Postgres while the channel's ticket is still live —
    # a webhook media URL dies within minutes, the DB copy does not.
    try:
        await run_in_threadpool(logs.save_media, ctx.get("channel"), None, message_id,
                                "image", image.content_type, blob)
    except logs.LogStoreError as exc:
        await _log("api", "warn", message=f"media archive failed: {exc}", **ctx)
    if report.has_data():
        chantier, chantier_source = await _resolve_chantier(report, ctx.get("technicien"))
        await run_in_threadpool(_notify_report_event, ctx.get("technicien"),
                                rapport_complet, warnings, ctx)
    else:
        # Nothing was extracted, so there is nothing to route: naming a site on
        # a message that filed no report would read as "filed to X".
        chantier, chantier_source = None, None
    return ProcessResponse(
        rapport_complet=rapport_complet, report=report, transcription=None, warnings=warnings,
        correlation_id=ctx.get("correlation_id"), message_id=message_id,
        chantier=chantier, chantier_source=chantier_source,
    )


async def _audio_input(
    audio: UploadFile,
    provider: Optional[str],
    caption: Optional[str],
    message_id: Optional[str],
    correlation_id: Optional[str],
    ctx: dict,
) -> Tuple[Optional[TranscriptionInfo], str, List[str], Optional[str]]:
    """Transcribe, archive the blob, mint the Drive link. Lifted out of
    `/process` so the endpoint reads as three input shapes, not one long
    branch — the archive and Drive steps are both best-effort, and their
    try/except pairs were most of that function's complexity."""
    transcription, rapport_complet, warnings, blob, media_id = await _transcribe_audio(
        audio, provider, ctx, message_id)
    if caption:
        rapport_complet = f"{rapport_complet}\n\n{caption}"
    # Archive the voice note (Postgres) and mint its durable link (Drive).
    # Both are best-effort: a log store outage or a Drive hiccup must never
    # cost the technician their summary — the fallback is the previous
    # behavior where n8n stored the channel's own file ticket.
    # media_id comes back from _transcribe_audio, which archived the blob before
    # the STT call — see the persist-first comment there. Not saved again here:
    # two rows for one voice note would show it twice in the dashboard.
    lien_audio = None
    try:
        if blob:
            lien_audio = await run_in_threadpool(
                drive.upload_audio,
                f"audio-{message_id or correlation_id or int(time.time())}.ogg",
                audio.content_type or DEFAULT_AUDIO_MIME, blob,
            )
    except drive.DriveError as exc:
        await _log("api", "warn", message=f"drive upload failed: {exc}", **ctx)
    # Tie the two copies together while we still hold both ids. This is the
    # only moment they are both in scope, and without it the Sheet's
    # `lien_audio` can never be resolved back to the blob we just stored — the
    # dashboard would be stuck playing through Drive, which does not work.
    if media_id and lien_audio:
        drive_id = drive.file_id_of(lien_audio)
        if drive_id:
            try:
                await run_in_threadpool(logs.link_media_drive, media_id, drive_id)
            except logs.LogStoreError as exc:
                await _log("api", "warn", message=f"media link failed: {exc}", **ctx)
    return transcription, rapport_complet, warnings, lien_audio


async def _resolve_chantier(report, technicien: Optional[str]):
    """Which site this message is headed for, resolved for the reply.

    The routing decision is only *taken* later, in /journal (reply-first
    ordering), so the technician was told "Rapport enregistré" and never learned
    which site it went to. A wrong site is the one error that silently moves a
    whole day onto the director's wrong sheet, and the only person who can catch
    it is the one standing on the site — but only if they are told.

    So this answers the question /journal will answer, from the same inputs and
    with the same precedence, read-only (`create=False`): the reply path must
    not write a chantier row for a report that may never be filed. The value is
    returned rather than glued onto `report.resume` — the Sheet's summary column
    stays a summary, and the routing line lives only in the reply n8n builds.

    Returns (nom, source), source being voix | repris | org | nouveau | aucun,
    or (None, None) when it cannot be answered — which must never cost the reply.
    """
    if not technicien:
        return None, None
    try:
        nom, _tab, _warnings, source = await run_in_threadpool(
            journal.resolve_site, technicien, report.chantier_mentionne, False
        )
    except Exception:  # noqa: BLE001  # a routing hint must never cost the reply
        return None, None
    return nom, source


async def _text_input(
    text: Optional[str], caption: Optional[str], message_id: Optional[str], ctx: dict,
) -> str:
    """Merge text + caption and archive the message. Empty after the merge is
    a 422 — an empty row is worse than a rejected one."""
    rapport_complet = (text or "").strip()
    if caption:
        rapport_complet = f"{rapport_complet}\n\n{caption}".strip()
    if not rapport_complet:
        await _log("api", "error", message="Empty text", **ctx)
        raise HTTPException(422, "Empty text")
    # Text messages are archived too, so the conversation is recoverable
    # even though the Sheet only keeps extracted reports.
    try:
        await run_in_threadpool(logs.save_message, ctx.get("channel"), None,
                                message_id, rapport_complet)
    except logs.LogStoreError as exc:
        await _log("api", "warn", message=f"chat archive failed: {exc}", **ctx)
    return rapport_complet


# n8n renders an absent expression as the STRING "null" in a multipart field,
# so an optional caption arrives as four characters of text rather than as
# nothing at all. `if caption:` is true for that string, and every voice note
# without a caption ended up with a literal "null" glued to the end of its
# transcript in the Sheet. Sanitised here rather than only in the workflow,
# because this is the trust boundary: any client can send it, and the fix has
# to hold for the one that has not been written yet.
_NULLISH = {"null", "undefined", "none", "nil", "nan", ""}


def _clean(value: Optional[str]) -> Optional[str]:
    """A client-supplied string, or None when it is a null spelled as text."""
    if value is None:
        return None
    stripped = value.strip()
    return None if stripped.lower() in _NULLISH else stripped


# What a vendor refusing on quota looks like, across Groq and Gemini. Matched on
# text because the chain raises a combined ExtractionError carrying each engine's
# own message and nothing more structured. Kept beside the endpoint that has to
# tell "everyone is rate-limited" apart from "this message is broken": the first
# must not spend a retry, the second must not get five more.
_QUOTA_RE = re.compile(
    r"429|quota|rate.?limit|RESOURCE_EXHAUSTED|exhausted|too many requests",
    re.I,
)


def _is_quota(detail: str) -> bool:
    return bool(_QUOTA_RE.search(detail or ""))


#: Header the retry job sets on its own call so the ordering gate lets it past.
#: It is the head of the queue by construction — gating it behind itself would
#: deadlock the technician permanently on their first failure.
QUEUE_BYPASS_HEADER = "X-Queue-Retry"


def _queue_bypass(request: Request) -> bool:
    return request.headers.get(QUEUE_BYPASS_HEADER) == "1"


def _input_kind(audio, image) -> str:
    """Which of the three shapes this message is, for the queue row."""
    if audio is not None:
        return "audio"
    if image is not None:
        return "image"
    return "text"


async def _park(reason: str, audio, image, text, caption,
                correlation_id, channel, technicien, message_id, ctx,
                detail: str = "") -> JSONResponse:
    """Queue this message for retry and answer 202, instead of failing it.

    Returns 202 rather than 502 on purpose: nothing is lost, so this is not an
    error — and n8n's error branch would send ❌ plus a failure message, which is
    exactly the wrong thing to tell a technician whose report is safely parked
    and will be filed. The reaction is set here, by the API, because n8n's
    synchronous call is over long before the retry resolves.

    Never raises: a queue that fails to accept a message must not also destroy
    the 502 the caller would otherwise have seen, so the fallback is that 502.
    """
    media_id = ctx.get("_media_id")
    item = _queue_item(
        _input_kind(audio, image),
        correlation_id=correlation_id, technicien=technicien, channel=channel,
        message_id=message_id,
        text_input=text if isinstance(text, str) else None,
        caption=caption, media_id=media_id,
        mime=getattr(audio or image, "content_type", None),
    )
    try:
        queue_id = await run_in_threadpool(logs.enqueue_message, item)
    except logs.LogStoreError as exc:
        await _log("api", "error", message=f"queue refused the message: {exc}", **ctx)
        raise HTTPException(502, detail or "processing failed") from exc
    await _log("queued", "warn",
               message=f"{reason}: {detail}"[:400], payload={"queue_id": queue_id}, **ctx)
    # 🪫 rather than 🔄 when every vendor is refusing on quota. Both mean "not
    # your fault, do nothing" — but they are different waits: a retry is minutes
    # and a spent free tier can be the rest of the day. Left on one symbol, a
    # quota block looked exactly like a message being processed right now, so
    # the technician eventually resends and one day of work becomes two rows.
    quota = _is_quota(detail)
    if channel and message_id:
        await run_in_threadpool(reply.set_reaction, channel,
                                str(ctx.get("chat_id") or "") or _chat_id_for(technicien, channel),
                                message_id, "quota" if quota else "queued")
    # Shaped like a ProcessResponse, not like an error. n8n reads
    # `Process output.item.json.report.resume` on the success path, and a body
    # without `report` made that expression evaluate to undefined and the reply
    # node die on "undefined is not valid JSON" — which, with reply-first
    # ordering, killed the run before /journal and lost the report entirely.
    # 202 keeps n8n on the success path deliberately; the payload has to keep
    # the promise that path makes.
    #
    # `queued` rides in `warnings` as well as at the top level, because the
    # reply text branches on warnings and that is where it can see it.
    return JSONResponse(
        status_code=202,
        content={
            "queued": True, "queue_id": queue_id, "reason": reason,
            "detail": detail[:400],
            # The reply text branches on warnings, so the distinction has to be
            # visible there too, not only in the reaction.
            "warnings": ["quota"] if quota else ["queued"],
            "report": {"resume": "Rapport reçu. Le service est momentanément "
                                 "indisponible : il sera enregistré "
                                 "automatiquement dès que possible."},
            "transcription": None,
            "chantier": None, "chantier_source": None,
            "rapport_complet": text if isinstance(text, str) else None,
        },
    )


def _chat_id_for(technicien: Optional[str], channel: Optional[str]) -> str:
    """The technician's own address on this channel, for a reaction.

    n8n knows it at reception; the API has to look it up, because a retry that
    resolves twenty minutes later has no request to read it from.
    """
    try:
        person = logs.person_by_name(technicien) if technicien else None
    except Exception:  # noqa: BLE001  # a reaction must never break the path
        return ""
    for ident in (person or {}).get("identities", []):
        if ident.get("channel") == channel and ident.get("active", True):
            return str(ident.get("external_id") or "")
    return ""


def _queue_item(kind: str, *, correlation_id, technicien, channel, message_id,
                text_input=None, caption=None, media_id=None, mime=None,
                sent_date=None, sent_heure=None) -> dict:
    return {"kind": kind, "correlation_id": correlation_id, "technicien": technicien,
            "channel": channel, "message_id": message_id, "text_input": text_input,
            "caption": caption, "media_id": media_id, "mime": mime,
            "sent_date": sent_date, "sent_heure": sent_heure}


async def _require_single_input(audio, image, text, ctx: dict) -> None:
    """422 unless exactly one of audio / image / text was sent."""
    provided = [name for name, value in (("audio", audio), ("image", image), ("text", text))
                if value is not None]
    if len(provided) == 1:
        return
    detail = f"Provide exactly one of 'audio', 'image' or 'text' (got: {provided or 'none'})"
    await _log("api", "error", message=detail, **ctx)
    raise HTTPException(422, detail)


async def _blocking_message(request, technicien, correlation_id) -> Optional[str]:
    """The correlation id this sender already has stuck in the queue, if any.

    The ordering gate. A message whose sender already has one parked joins it
    behind that one instead of being processed now — otherwise message 2 is
    filed before message 1 the moment message 1 fails, and the journal records
    the technician's day out of order. Checked here, in the one place every
    message passes through, rather than in n8n: the retry job comes through the
    same door and must obey the same rule.
    `_queue_bypass` is how the retry job says "I *am* the head of that queue".
    """
    if request is None or _queue_bypass(request) or not settings.database_url:
        return None
    try:
        blocked = await run_in_threadpool(logs.blocked_technician, technicien)
    except logs.LogStoreError:
        return None  # no store, no ordering to enforce — never fail closed
    if blocked and blocked.get("correlation_id") != correlation_id:
        return blocked["correlation_id"]
    return None


async def _route_report(report, technicien, rapport_complet, warnings, ctx) -> tuple:
    """Site this report belongs to, and the bell that goes with it.

    "salut" extracts to an all-null report. Without this the pipeline appends
    an empty Sheet row and answers "✅ Rapport enregistré" for a greeting —
    and nothing was extracted, so there is nothing to route: naming a site on
    a message that filed no report would read as "filed to X".
    """
    if not report.has_data():
        warnings.append("no_report_content")
        return None, None
    chantier, chantier_source = await _resolve_chantier(report, technicien)
    # psycopg2 is synchronous, like every other DB call on this path: run it
    # off the event loop so one technician's notification does not stall
    # every other request in flight. Same reason as _log() above.
    await run_in_threadpool(_notify_report_event, technicien,
                            rapport_complet, warnings, ctx)
    return chantier, chantier_source


@app.post("/process", responses={422: {"description": "Invalid input"}, 502: {"description": "Upstream service error"}})
async def process(
    audio: Optional[UploadFile] = File(None, description="Voice note (ogg/opus from WhatsApp)"),
    image: Optional[UploadFile] = File(None, description="Photo: notebook page, whiteboard, delivery note, or the work itself"),
    text: Optional[str] = Form(None, description="Raw report text (web form mode)"),
    caption: Optional[str] = Form(None, description="Text that came with the audio/image (Telegram captions) — merged into the input before extraction"),
    provider: Optional[str] = Form(None, description="STT engine override (benchmark use)"),
    correlation_id: Optional[str] = Form(None, description="Trace id minted by n8n at reception"),
    channel: Optional[str] = Form(None, description="telegram | whatsapp | form"),
    technicien: Optional[str] = Form(None, description="Sender name, for log filtering"),
    message_id: Optional[str] = Form(None, description="Channel message id (dedupe key, e.g. 'tg:123:456')"),
    request: Request = None,  # type: ignore[assignment]
    caller: dict = Depends(auth.require_user),
) -> ProcessResponse:
    caption = _clean(caption)
    text = _clean(text)
    # Same trace id n8n threads through every stage, so the API's own errors
    # line up with the workflow's rows in the dashboard timeline.
    ctx = {"correlation_id": correlation_id, "channel": channel, "technicien": technicien}
    # Nightly summary of this technician (app/memory.py), injected as context.
    # Best effort on purpose: an unknown sender or a log store outage must
    # degrade to plain extraction, not fail a report someone is waiting for.
    try:
        sender_profile = await run_in_threadpool(logs.profile_for, technicien)
    except logs.LogStoreError:
        sender_profile = None

    await _require_single_input(audio, image, text, ctx)

    # A caption is auxiliary: it never satisfies the "exactly one input" rule,
    # but once an input exists it rides along as part of the message. Telegram
    # sends it when a technician records a voice note with a text caption.
    caption = (caption or "").strip() or None

    lien_audio = None  # set only by the audio branch (Drive upload)

    ahead = await _blocking_message(request, technicien, correlation_id)
    if ahead:
        return await _park(
            "blocked", audio, image, text, caption, correlation_id,
            channel, technicien, message_id, ctx,
            detail=f"en attente derrière {ahead}",
        )

    if audio is not None:
        try:
            transcription, rapport_complet, warnings, lien_audio = await _audio_input(
                audio, provider, caption, message_id, correlation_id, ctx,
            )
        except HTTPException as exc:
            if exc.status_code != 502:
                raise  # 422 is malformed input: it will never succeed, do not queue
            return await _park("stt", audio, image, text, caption,
                               correlation_id, channel, technicien, message_id, ctx,
                               detail=str(exc.detail))
    elif image is not None:
        return await _extract_from_image(image, sender_profile, caption, ctx, message_id)
    else:
        transcription = None
        warnings = []
        rapport_complet = await _text_input(text, caption, message_id, ctx)

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
        # The transcript survived even though extraction did not, so the retry
        # replays text rather than audio: re-transcribing would spend an STT call
        # to recompute something already in hand, and could yield a *different*
        # transcript than the one the technician's summary was promised from.
        # Prefix kept: with no log store the queue cannot accept the message and
        # _park re-raises this as the 502 it replaces, so the wording is still
        # part of the endpoint's contract.
        return await _park("extraction", None, None, rapport_complet, caption,
                           correlation_id, channel, technicien,
                           message_id, ctx, detail=f"extraction failed: {exc}")

    chantier, chantier_source = await _route_report(
        report, technicien, rapport_complet, warnings, ctx)

    await _log(
        "extracted", "info", message="ok",
        duration_ms=int((time.time() - t1) * 1000),
        payload={"model": model_used, "etages": report.etages}, **ctx,
    )

    return ProcessResponse(
        rapport_complet=rapport_complet,
        report=report,
        transcription=transcription,
        warnings=warnings,
        lien_audio=lien_audio,
        correlation_id=correlation_id,
        message_id=message_id,
        chantier=chantier,
        chantier_source=chantier_source,
    )


# ── media + chat archive (TO-DO #10: download audios/images/chat to the DB) ─

@app.get("/media", responses={502: {"description": "Log store unreachable"}})
def list_media(
    limit: int = Query(50, ge=1, le=500), caller: dict = Depends(auth.require_human)
) -> dict:
    """Archive listing (metadata only, never the blobs)."""
    try:
        return {"media": logs.list_media(limit)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/media/{media_id}/file", responses={404: {"description": "Not found"}, 502: {"description": "Log store unreachable"}})
def get_media_file(
    media_id: int, request: Request, caller: dict = Depends(auth.require_human)
) -> Response:
    """One archived voice note / photo, for the dashboard's <audio>/<img> tags.

    Shares `_media_response` with `/audio/{drive_id}`: this route used to hand
    back the stored `mime_type` as-is and no Range header, which is silent
    death for a voice note — Telegram labels them `application/octet-stream`
    often enough that the player had nothing to decode, and without Range
    Safari refuses to start at all.
    """
    try:
        row = logs.get_media(media_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "media not found")
    return _media_response(row["data"], row["mime_type"] or "", request,
                           filename=f"media-{row['id']}")


@app.get("/messages", responses={502: {"description": "Log store unreachable"}})
def list_messages(
    limit: int = Query(100, ge=1, le=500), channel: Optional[str] = None, search: Optional[str] = None,
    caller: dict = Depends(auth.require_human),
) -> dict:
    """Raw chat archive, newest first — the Sheet only keeps extracted reports."""
    try:
        return {"messages": logs.list_messages(limit, channel, search)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc




# No auth: dashboard + API run only on the admin's machine (localhost), decided 2026-07-23.
@app.get("/reports", responses={502: {"description": "Sheets read failed"}})
def list_reports(caller: dict = Depends(auth.require_human)) -> dict:
    """The Rapports feed, with its figures put back on.

    Rapports holds only the index columns since 2026-08-19 — when, who, where,
    what was said, a way back to the message. The quantities live in
    `report_rows`, so they are merged back in here under the header names the
    dashboard has always read (`goulottes_m`, `cables_m`, …): the split is a
    storage decision and the browser should not have to know about it.

    Best-effort on the Postgres side. A figure that cannot be fetched leaves the
    row without it, exactly as an empty cell did; it must never turn the whole
    feed into a 502, because the feed is also the inbox.
    """
    try:
        rows = sheets.read_reports()
    except sheets.SheetsError as exc:
        raise HTTPException(502, f"sheets read failed: {exc}") from exc
    try:
        renames = journal.RAPPORTS_RENAMES
        figures = {
            r["correlation_id"]: r
            for r in logs.list_report_rows()
            if r.get("correlation_id")
        }
        for row in rows:
            extra = figures.get((row.get("correlation_id") or "").strip())
            if not extra:
                continue
            for field in journal.DATA_FIELDS:
                value = extra.get(field)
                if value in (None, [], ""):
                    continue
                row.setdefault(
                    renames.get(field, field),
                    ", ".join(str(v) for v in value) if isinstance(value, list) else value,
                )
    except Exception as exc:  # noqa: BLE001  # figures are a bonus, the feed is not
        logs.write_safe("api", "error", message=f"/reports figure merge failed: {exc}")
    return {"reports": rows}


@app.get("/reports/generated", responses={502: {"description": "Log store unreachable"}})
def list_generated_reports(caller: dict = Depends(auth.require_human)) -> dict:
    """The daily + weekly reports the scheduler stored, newest first.

    These are the exact texts that were mailed and that /rapport answers
    with — the dashboard shows them so an operator sees the reports without
    digging in an inbox.
    """
    try:
        return {"reports": logs.list_manager_reports()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"log store read failed: {exc}") from exc


KINDS = ("daily", "weekly")


@app.get(
    "/report-versions",
    responses={
        422: {"description": "Unknown kind"},
        502: {"description": "Log store unreachable"},
    },
)
def list_report_versions(
    kind: str = Query(..., description="daily | weekly"),
    period: str = Query(..., description="La date, ou le premier jour de la semaine"),
    full: bool = Query(False, description="Inclure le corps et l'image de chaque version"),
    manager_id: int = Query(
        0,
        description="0 = rapport de la société; -1 = tous; sinon le chef concerné",
    ),
    caller: dict = Depends(auth.require_human),
) -> dict:
    """The editing history of one report, newest first.

    Defaults to the index without bodies: the dashboard draws a list of saves
    on every open and reads a single old version only when one is clicked.
    """
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {KINDS}")
    try:
        return {
            "versions": logs.list_report_versions(
                kind, period, with_body=full,
                # Negative means "any manager" — the Daily and Weekly panels ask
                # which document went out for a period, not whose it was.
                manager_id=None if manager_id < 0 else manager_id,
            )
        }
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"log store read failed: {exc}") from exc


@app.get(
    "/report-versions/{version_id}/docx",
    responses={404: {"description": "No stored document for this version"}},
)
def report_version_docx(
    version_id: int,
    download: bool = Query(False, description="Télécharger plutôt qu'afficher"),
    caller: dict = Depends(auth.require_human),
) -> Response:
    """The .docx exactly as it was rendered when this version was saved.

    Read from the row, never re-rendered: the figures come from the rows the
    period covers and those keep changing, so a re-render of an old version is
    a document nobody ever received. A version stored before the column existed
    (or whose render failed) has none, and 404 is the honest answer — the
    dashboard falls back to exporting the current text, and says so.
    """
    try:
        found = logs.report_version_docx(version_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"log store read failed: {exc}") from exc
    if found is None:
        raise HTTPException(404, "aucun document stocké pour cette version")
    objet, blob = found
    return _docx_response(docx_report.filename(objet), blob, inline=not download)


class ReportVersionIn(BaseModel):
    kind: str = Field(..., description="daily | weekly")
    period: str = Field(..., description="La date, ou le premier jour de la semaine")
    objet: str
    corps: str
    image: Optional[str] = Field(default=None, description="Carte illustrée, en data: URI")
    note: Optional[str] = None
    manager_id: int = Field(
        default=0, description="0 = rapport de la société; sinon le chef concerné"
    )


@app.post(
    "/report-versions",
    status_code=201,
    responses={
        422: {"description": "Unknown kind, or an empty objet or corps"},
        502: {"description": "Log store unreachable"},
    },
)
def save_report_version(payload: ReportVersionIn, caller: dict = Depends(auth.require_human)) -> dict:
    """Append one saved version. Never overwrites: history is the feature."""
    if payload.kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {KINDS}")
    if not payload.objet.strip():
        raise HTTPException(422, "objet must not be empty")
    if not payload.corps.strip():
        raise HTTPException(422, "corps must not be empty")
    author = caller.get("name") or "inconnu"

    # The document is rendered here and stored with the text it came from, so
    # the version *is* the .docx and not a promise to rebuild one later. The
    # provenance line inside it carries `author`, which is how "who made the
    # last change" ends up in the report itself rather than only in a table
    # beside it. Best-effort: a renderer that fails must not cost the operator
    # the edit they just made — the version is still saved, without a document,
    # and the dashboard falls back to exporting the current text.
    # `edited=True`: this render is a human's correction, and the provenance
    # line inside the document says "modifié par" rather than "établi par".
    blob = _safe_docx(payload.objet, payload.corps, payload.period, author, edited=True)

    try:
        version = logs.save_report_version(
            kind=payload.kind,
            period=payload.period,
            objet=payload.objet,
            corps=payload.corps,
            image=payload.image,
            author=author,
            note=payload.note,
            manager_id=payload.manager_id,
            docx=blob,
        )
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"log store write failed: {exc}") from exc

    # The Reports page reads `manager_reports`, so an edit that stayed only in
    # `report_versions` would leave that page showing the model's draft while
    # the manager was looking at their corrected text. The version history is
    # the append-only record; this is the "current text" the rest of the app
    # reads, so the newest save wins here.
    # Filed under the manager the report belongs to, not under whoever typed
    # the correction: `manager_reports` is keyed (manager, period) and is what
    # the Reports page and the technicians read, so mirroring an edit of a
    # chef's report onto the editor's own id would leave the chef's row showing
    # the model's draft and create a second, duplicate report under the editor.
    # `generated_by` still names the person who changed it — that is the "who
    # made the last change" the report itself prints.
    owner = payload.manager_id or caller.get("id")
    if owner:
        try:
            logs.save_manager_report(
                owner,
                payload.period,
                payload.objet,
                payload.corps,
                author,
                payload.kind,
            )
        except logs.LogStoreError as exc:
            # Swallowed on purpose — the version itself is already stored and an
            # unreachable log store must not cost the operator their edit. Said
            # out loud, though: a bare `pass` here is exactly how the Reports
            # page stayed empty for a whole session with nothing to read.
            print(f"[reports] mirror to manager_reports failed: {exc}")

    auth.record(caller, "report_version_saved", target=f"{payload.kind} {payload.period}")
    return version


class ReportPatch(BaseModel):
    field: str
    value: Optional[str] = None


@app.patch("/reports/{row}", responses={422: {"description": "Invalid input"}, 502: {"description": "Sheets write failed"}})
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


class DailyReportResponse(BaseModel):
    """The generated report plus who asked for it — provenance rides alongside."""

    objet: str
    corps: str
    generated_by: str


@app.post("/daily-report", responses={422: {"description": "No rows for the given date"}, 502: {"description": "Daily report generation failed"}})
def daily_report_endpoint(payload: DailyReportRequest, caller: dict = Depends(auth.require_user)) -> DailyReportResponse:
    auth.record(caller, "report_generated", target=payload.date)
    if not payload.rows:
        raise HTTPException(422, "No rows for the given date")
    try:
        content = daily_report.generate_daily_report(
            payload.date, payload.rows, stock.alerts_for_rows(payload.rows)
        )
    except daily_report.DailyReportError as exc:
        raise HTTPException(502, f"daily report failed: {exc}") from exc
    # Store it, exactly as the scheduler does with its own runs.
    #
    # Without this a report generated from the dashboard existed only in the
    # browser tab that asked for it: the Reports page reads `manager_reports`,
    # so a manager pressed "générer", read the report, navigated away and found
    # the list empty — the feature looked broken because two paths produced
    # reports and only one of them wrote anything down.
    #
    # It is filed under the caller: a dashboard run covers the whole company
    # rather than one chef's crew, and the person who asked for it is the
    # honest owner. A weekly run reaches this same endpoint with a range label
    # (`2026-08-03 → 2026-08-09`), which is what distinguishes the two periods.
    period_type = "weekly" if "→" in payload.date else "daily"
    if caller.get("id"):
        try:
            logs.save_manager_report(
                caller["id"], payload.date, content.objet, content.corps, caller["name"], period_type
            )
        except logs.LogStoreError as exc:
            # An unreachable log store must not cost the operator their report,
            # but it does cost the Reports page this row — so it is printed.
            print(f"[reports] storing the generated report failed: {exc}")

    # …and as version 1 of that period's history, with the document it renders
    # to. Filed under the *same* id as the `manager_reports` row above, because
    # the two are one report seen from two pages: the Reports page lists the
    # row and the editor beside it reads this history, and keying them
    # differently is how a report shows "no versions" next to a version it
    # generated itself. Without this the history began at the first human
    # correction, so the model's own wording — the thing an edit is judged
    # against — was the one version never stored.
    try:
        logs.save_report_version(
            kind=period_type,
            period=payload.date,
            objet=content.objet,
            corps=content.corps,
            author=caller.get("name") or "automatique",
            manager_id=caller.get("id") or 0,
            docx=_safe_docx(content.objet, content.corps, payload.date, caller.get("name")),
        )
    except logs.LogStoreError as exc:
        print(f"[reports] archiving the generated version failed: {exc}")

    # The scheduled mail is signed "automatique"; a manual run is signed by the
    # account that asked — the dashboard shows it next to the panel.
    return DailyReportResponse(
        objet=content.objet, corps=content.corps, generated_by=caller["name"]
    )


class ReportExportRequest(BaseModel):
    """What the dashboard's Export button sends: the text, not the figures.

    The body travels because the operator may have edited the draft before
    exporting — that edited text *is* the report. The figures deliberately do
    not: they are recomputed from the Sheet rows the period covers, so the
    document and the page cannot disagree and a client cannot post numbers of
    its own choosing into a document signed with the company header.
    """

    title: str = Field(..., description="Titre du document (l'objet du rapport)")
    body: str = Field(..., description="Corps du rapport, avec ses '## ' et ses '- '")
    period: str = Field(..., description="Jour (2026-08-16) ou plage (2026-08-10 → 2026-08-16)")
    author: Optional[str] = Field(None, description="Qui l'a établi; absent = automatique")


def render_report_docx(
    title: str, body: str, period: str, author: Optional[str], edited: bool = False
) -> bytes:
    """The report as a .docx — the same bytes the scheduled mail attaches.

    The renderer lives in the backend (`docx_report.py`) because `jobs.py` sends
    the scheduled report from a thread with no browser to build a document in.
    The dashboard therefore downloads this rather than assembling its own copy:
    two renderers of one document drift, and only one of them is ever the one
    the director received.

    A function rather than only a handler since 2026-08-21: saving a version
    stores the document it produced, and a stored version has to be rendered on
    exactly the path the download uses or the two would be different documents
    under one version number.
    """
    weekly = "→" in period
    # A weekly label carries its two ends (`2026-08-10 → 2026-08-16`) and every
    # day between them belongs; a daily one is the single day. Both sides go
    # through `norm_date` because the Sheet hands back `10/08/2026` once the
    # column is formatted as a date, and a string compare would drop the week.
    first, _, last = period.partition("→")
    start = journal.norm_date(first) or ""
    end = (journal.norm_date(last) if weekly else start) or start

    # Postgres, not the Sheet. The Rapports tab deliberately carries **no
    # quantity columns** since 2026-08-19 — it is the index a human reads, and
    # the figures moved to `report_rows` where they cost no Google read. This
    # handler kept reading the tab, so `rapports_totals` looked up schema-named
    # keys that are not in those rows and every quantity in the exported
    # document came back empty: an export and the scheduled mail for the same
    # period disagreed, and only the mail was right. `jobs._period_report`
    # already sources its rows this way; both paths now read the same store.
    # Filtered here rather than by `dates=` in SQL, deliberately. `resolve_date`
    # falls back to the transmitted date **unnormalised** when the stated one is
    # unusable, so `report_rows.date` can hold `12/08/2026` beside `2026-08-12`;
    # an exact `date = ANY(...)` match would drop those rows silently, which is
    # the same class of bug the Sheet spelling caused and that `norm_date`
    # exists to close.
    try:
        rows = [
            r for r in logs.list_report_rows()
            if (day := journal.norm_date(r.get("date"))) and start <= day <= end
        ]
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"lecture des rapports impossible: {exc}") from exc

    return docx_report.build(
        title,
        body,
        "Rapport hebdomadaire" if weekly else "Rapport journalier",
        period,
        rows,
        author=author,
        edited=edited,
        # The same assessment the mail carries, so a document exported by
        # hand and one attached by the scheduler say the same thing.
        alerts=stock.alerts_for_rows(rows),
    )


def _safe_docx(
    title: str, body: str, period: str, author: Optional[str], edited: bool = False
) -> Optional[bytes]:
    """`render_report_docx`, but a failure costs the document and nothing else.

    Used on the paths where the document is a by-product — archiving a version
    — as opposed to the download, where a failure *is* the answer and has to
    reach the operator.
    """
    try:
        return render_report_docx(title, body, period, author, edited)
    except Exception as exc:  # noqa: BLE001
        print(f"[reports] .docx render failed: {exc}")
        return None


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_response(name: str, blob: bytes, inline: bool = False) -> Response:
    """One document, as a download or as something a viewer can render.

    `inline` is what the dashboard's preview asks for: the same bytes, but the
    browser is told to show them rather than to save them — the preview and the
    download must never be two different renders of one report.
    """
    disposition = "inline" if inline else "attachment"
    return Response(
        blob,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'{disposition}; filename="{name}"'},
    )


@app.get(
    "/reports/document",
    responses={
        404: {"description": "No report stored for this period"},
        422: {"description": "Unknown kind"},
    },
)
def latest_report_document(
    kind: str = Query(..., description="daily | weekly"),
    period: str = Query(..., description="Jour (2026-08-16) ou plage (2026-08-10 → 2026-08-16)"),
    caller: dict = Depends(auth.require_human),
) -> Response:
    """The document for a period, whoever produced it.

    Stored bytes when a version has them — that is the file that was mailed and
    it is served untouched. Otherwise the newest stored *text* for the period is
    rendered now, which is the only way the reports that predate the `docx`
    column (or whose render failed at the time) are visible at all: without this
    fallback the Daily page of every past day would show nothing and read as
    broken, when in fact the report exists and only its file does not.

    The fallback's figures are recomputed from today's rows and can therefore
    differ from what was originally sent; that is why it is a fallback and not
    the path a version takes.
    """
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {KINDS}")
    try:
        versions = logs.list_report_versions(kind, period, with_body=False, manager_id=None)
        stored = next((v for v in versions if v.get("has_docx")), None)
        if stored:
            found = logs.report_version_docx(stored["id"])
            if found:
                objet, blob = found
                return _docx_response(docx_report.filename(objet), blob, inline=True)

        weekly = kind == "weekly"
        row = next(
            (
                r for r in logs.list_manager_reports()
                if r.get("period") == period and (r.get("period_type") == "weekly") == weekly
            ),
            None,
        )
    except logs.LogStoreError as exc:
        raise HTTPException(502, f"log store read failed: {exc}") from exc
    if row is None:
        raise HTTPException(404, "aucun rapport pour cette période")

    blob = render_report_docx(row["objet"], row["corps"], period, row.get("generated_by"))
    return _docx_response(docx_report.filename(row["objet"]), blob, inline=True)


@app.post("/reports/export", responses={502: {"description": "Sheets read failed"}})
def export_report(payload: ReportExportRequest, caller: dict = Depends(auth.require_human)) -> Response:
    """The Export button: render the current text and hand it back as a file."""
    blob = render_report_docx(
        payload.title, payload.body, payload.period, payload.author or caller.get("name")
    )
    auth.record(caller, "report_exported", target=payload.period)
    return _docx_response(docx_report.filename(payload.title), blob)


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


@app.post("/logs", responses={502: {"description": "Log store unreachable"}})
def create_log(event: LogEvent, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        log_id = logs.write(**event.model_dump())
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "id": log_id}


@app.get("/logs", responses={502: {"description": "Log store unreachable"}})
def list_logs(
    limit: int = Query(200, ge=1, le=1000),
    level: Optional[str] = None,
    channel: Optional[str] = None,
    stage: Optional[str] = None,
    correlation_id: Optional[str] = None,
    search: Optional[str] = None,
    caller: dict = Depends(auth.require_user),
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


@app.get("/in-flight", responses={502: {"description": "Log store unreachable"}})
def messages_in_flight(minutes: int = 15, caller: dict = Depends(auth.require_user)) -> dict:
    """Messages received and not yet answered — the inbox's ⏳ per sender.

    Read off `pipeline_logs` rather than a table of its own: the rows that say
    a message arrived and that it was answered are already written on every
    run, and a dedicated in-flight table would need a sweeper for every crash
    between the two.
    """
    try:
        return {"in_flight": logs.in_flight(minutes)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/logs", responses={502: {"description": "Log store unreachable"}})
def prune_logs(days: int = logs.RETENTION_DAYS, caller: dict = Depends(auth.require_director)) -> dict:
    """Retention sweep, called by the daily cron workflow."""
    try:
        return {"deleted": logs.prune(days)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ExchangeInput(BaseModel):
    date: Optional[str] = None
    heure: Optional[str] = None
    channel: Optional[str] = None
    external_id: Optional[str] = None
    message_id: Optional[str] = None
    technicien: Optional[str] = None
    kind: str = "text"
    text: Optional[str] = None
    reply: Optional[str] = None
    correlation_id: Optional[str] = None
    # Which STT engine heard this note, for the audio rows. The Rapports mirror
    # records it as `STT_model`; an exchange never becomes a Rapports row, so
    # without this the inbox shows the engine for filed reports only.
    stt_engine: Optional[str] = None


@app.post("/exchanges", responses={502: {"description": "Log store unreachable"}})
def record_exchange(exchange: ExchangeInput, caller: dict = Depends(auth.require_user)) -> dict:
    """One exchange that produced no Sheet row, written by n8n after the reply.

    Best-effort by design: it runs on the no_report_content branch, so a
    failure here must never surface to the technician who just got their
    answer.
    """
    try:
        exchange_id = logs.save_exchange(**exchange.model_dump())
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "id": exchange_id}


@app.get("/exchanges", responses={502: {"description": "Log store unreachable"}})
def list_exchanges(
    limit: int = Query(200, ge=1, le=500),
    caller: dict = Depends(auth.require_user),
) -> dict:
    """The conversation log — exchanges that never became Sheet rows, newest
    first. The inbox merges these with the Rapports feed to show the complete
    conversation; `media_id` lets it play the voice note."""
    try:
        return {"exchanges": logs.list_exchanges(limit=limit)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ExchangePatch(BaseModel):
    """The corrected transcript of a logged exchange."""

    text: str = Field(..., max_length=20_000)


@app.patch("/exchanges/{exchange_id}", responses={404: {"description": "Exchange not found"}, 502: {"description": "Log store unreachable"}})
def patch_exchange(exchange_id: int, payload: ExchangePatch,
                   caller: dict = Depends(auth.require_human)) -> dict:
    """Correct what a voice note was heard as.

    The inbox shows the transcript under the audio and lets an operator fix it,
    for the same reason the Sheet's `rapport_complet` is editable through
    `PATCH /reports/{row}`: Darija through an STT engine gets names and numbers
    wrong, and the person listening to the recording is the only one who can
    say so. The correction is recorded with its previous value, so the raw
    machine output is still recoverable from the audit trail and the extraction
    stays auditable — which was the original reason the transcript was
    read-only.
    """
    try:
        result = logs.update_exchange_text(exchange_id, payload.text)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "exchange introuvable")
    auth.record(
        caller, "transcript_edited", target=f"exchange {exchange_id}",
        before=result["before"], after=payload.text,
    )
    return {"ok": True}


class ClaimRequest(BaseModel):
    message_id: str
    channel: Optional[str] = None


@app.post("/logs/claim", responses={502: {"description": "Log store unreachable"}})
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


# ── Journal write ──────────────────────────────────────────────────────────
# The Sheet write moved out of n8n and into here, because filing a report is no
# longer an append: a second message from the same technician the same day
# merges into their existing row, and stock has to be reconciled against the
# last known level on the chantier. An IF node cannot read-modify-write a tab.
#
# What did NOT move is the ordering. n8n still replies to the technician first
# and calls this afterwards, so a Sheets outage costs a row (parked in
# `failed_writes`, drained every 5 minutes) and never a technician's summary.


class JournalEntry(BaseModel):
    report: dict
    technicien: str
    date: str
    heure: Optional[str] = None
    canal: Optional[str] = None
    role: Optional[str] = None
    chantier: Optional[str] = None
    rapport_complet: Optional[str] = None
    lien_audio: Optional[str] = None
    correlation_id: Optional[str] = None
    message_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    stt_engine: Optional[str] = Field(
        default=None,
        description=(
            "Moteur STT qui a effectivement transcrit (transcription.provider de "
            "/process). Absent pour un rapport texte ou photo. Le moteur réel, pas "
            "l'ordre configuré : la chaîne bascule en cas d'échec."
        ),
    )


@app.post("/journal", responses={
    422: {"description": "Charge utile du journal invalide"},
    502: {"description": "Sheets unreachable"},
})
async def file_journal_entry(
    entry: JournalEntry, caller: dict = Depends(auth.require_user)
) -> dict:
    """File one report into its chantier's journal tab.

    A Sheets failure is a 502 *and* a parked row: n8n does not have to decide
    what to do with the error, and the drain picks it up. Returning the row
    number lets a later `/modify` find what the technician just reported.
    """
    payload = entry.model_dump()
    try:
        result = await run_in_threadpool(journal.file_report, payload)
    except ValidationError as exc:
        # `report` is an unvalidated dict here on purpose (its schema is
        # journal.file_report's business), so an unrecognized étage or aile
        # raises out of ExtractedReport rather than out of FastAPI's own
        # parsing. Deliberately *not* parked: no amount of retrying makes a
        # payload parse, and reply-first means the technician has already been
        # told it landed — so it has to be visible in the log instead of a 500
        # with nothing behind it. 422, not 502: the input is the problem.
        logs.write_safe("sheet", "error", message=f"journal payload rejected: {exc}",
                        correlation_id=entry.correlation_id)
        raise HTTPException(422, f"journal payload rejected: {exc}") from exc
    except sheets.SheetsError as exc:
        try:
            logs.queue_failed_write(payload, str(exc), entry.correlation_id)
        except logs.LogStoreError as queue_exc:
            logs.write_safe("api", "error", message=f"queue failed: {queue_exc}")
        logs.write_safe("sheet", "error", message=f"journal write failed: {exc}",
                        correlation_id=entry.correlation_id)
        raise HTTPException(502, f"journal write failed: {exc}") from exc

    if entry.message_id and result.get("row"):
        try:
            logs.link_message_row(entry.message_id, result.get("rapports_row"))
        except logs.LogStoreError:
            pass  # best-effort: the row is written, the link is a convenience
    logs.write_safe(
        "sheet", "info",
        message=f"journal row {result.get('row')} ({result.get('tab')})"
                + (" [duplicate]" if result.get("duplicate") else ""),
        correlation_id=entry.correlation_id,
    )
    return result


# ── Audio playback ─────────────────────────────────────────────────────────


def _sniff_mime(data: bytes) -> str:
    """The real content type, read from the magic bytes."""
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "audio/mpeg"


def _range_bounds(match, total: int) -> tuple:
    """First and last byte a `Range:` header asks for."""
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else total - 1
        return start, end
    # `bytes=-N` is the *last* N bytes, not "from N".
    return max(0, total - int(match.group(2))), total - 1


def _media_response(data: bytes, mime: str, request: Request,
                    filename: Optional[str] = None) -> Response:
    """Bytes a media element can actually play, Range included.

    Two things kill a voice note silently, and both are handled here so no
    route can forget one:

    * The stored MIME. Telegram voice notes are labelled
      `application/octet-stream` often enough that trusting it leaves the
      element with nothing to decode — and a media element that cannot decode
      raises no error, it simply never plays. Sniffed from the magic bytes
      instead, falling back to mpeg.
    * Range. Without `accept-ranges` and a real 206, Chrome plays but will not
      seek, and Safari does not start at all. The whole file is already in
      memory, so a range is a slice rather than a second fetch.
    """
    total = len(data)
    if not mime.startswith(("audio/", "image/")):
        mime = _sniff_mime(data)

    headers = {"accept-ranges": "bytes", "cache-control": "private, max-age=3600"}
    if filename:
        headers["content-disposition"] = f'inline; filename="{filename}"'

    rng = request.headers.get("range", "")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip()) if rng else None
    if match and (match.group(1) or match.group(2)):
        start, end = _range_bounds(match, total)
        if start >= total:
            # 416 must advertise the real length or the player retries forever.
            return Response(
                status_code=416, headers={**headers, "content-range": f"bytes */{total}"}
            )
        end = min(end, total - 1)
        headers["content-range"] = f"bytes {start}-{end}/{total}"
        return Response(data[start : end + 1], status_code=206, media_type=mime,
                        headers=headers)

    return Response(data, media_type=mime, headers=headers)


@app.get("/audio/row/{rapports_row}", responses={
    404: {"description": "No audio archived"},
    502: {"description": "Log store unreachable"},
})
async def stream_audio_for_row(
    rapports_row: int, request: Request, caller: dict = Depends(auth.require_user)
) -> Response:
    """Play the voice note behind a Rapports row, straight from Postgres.

    The route for the rows `/audio/{drive_id}` cannot serve: the Drive upload
    is best-effort, so an outage leaves the Sheet row with no `lien_audio` and
    the dashboard with nothing to point at — while the blob has been sitting in
    `media_files` since the message arrived. A 404 here means we genuinely do
    not hold one, which is the honest answer and lets the Inbox render the
    message as text rather than an audio player that will never sound.
    """
    try:
        row = await run_in_threadpool(logs.find_media_by_rapports_row, rapports_row)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no audio archived for this row")
    return _media_response(row["data"], row["mime_type"] or "", request)


@app.get("/audio/{file_id}", responses={502: {"description": "Drive unreachable"}})
async def stream_audio(
    file_id: str, request: Request, caller: dict = Depends(auth.require_user)
) -> Response:
    """Play one voice note from Drive.

    The Inbox used to point `<audio src>` straight at the `lien_audio` share
    link and nothing ever played: Drive answers that URL with a redirect chain,
    `Content-Disposition: attachment` and no Range support, so the media
    element gets something it cannot decode and fails silently — no error, no
    sound. This hands the browser the actual bytes with an audio content type.

    Range is answered properly rather than ignored: without it Chrome will
    play a voice note but refuse to seek in it, and Safari will not play it at
    all. The whole file is already in memory (see `drive.download`), so a range
    is a slice, not a second fetch.

    Gated like everything else — `require_user`, so the bytes are not public
    even though the Drive file's own permission still is.

    Postgres first, Drive second. `/process` archives every voice note into
    `media_files` as it arrives and records the Drive id it was published
    under, so the copy we already hold is the one that answers — no network
    call, no dependency on Drive being reachable or the file still existing.
    Drive stays as the fallback for rows archived before the link column
    existed, and for the case where the blob was pruned by retention but the
    Sheet link lives on.
    """
    data: Optional[bytes] = None
    mime = ""
    try:
        row = await run_in_threadpool(logs.find_media_by_drive_id, file_id)
        if row:
            data, mime = row["data"], row["mime_type"] or ""
    except logs.LogStoreError as exc:
        # Not fatal: the Drive path below is exactly the fallback for this.
        logs.write_safe("api", "warn", message=f"media lookup failed: {exc}")

    if data is None:
        try:
            data, mime = await run_in_threadpool(drive.download, file_id)
        except drive.DriveError as exc:
            raise HTTPException(502, str(exc)) from exc

    return _media_response(data, mime, request)


# ── Sheet retry queue ──────────────────────────────────────────────────────
# Reply-first means the Sheet write is a recoverable side effect: failures park
# here and the cron workflow drains them, so no report is lost to a Google outage.


class FailedWrite(BaseModel):
    payload: dict
    error: str
    correlation_id: Optional[str] = None


@app.post("/sheet-queue", responses={502: {"description": "Log store unreachable"}})
def queue_write(item: FailedWrite, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        queued_id = logs.queue_failed_write(item.payload, item.error, item.correlation_id)
        # The bell: a write parked in the retry queue means the Sheet is (or
        # was) behind — the directeur learns now, not at the daily digest.
        try:
            logs.notify_managers(
                "error",
                "Échec d'écriture Google Sheets",
                f"Un rapport n'a pas pu être écrit (file d'attente {queued_id}).",
                "#/logs", item.correlation_id,
            )
        except logs.LogStoreError as exc:
            logs.write_safe("api", "warn", message=f"notification failed: {exc}")
        return {"id": queued_id}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class CursorIn(BaseModel):
    value: Any


@app.get("/cursor/{name}", responses={502: {"description": "Log store unreachable"}})
def read_cursor(name: str, caller: dict = Depends(auth.require_user)) -> dict:
    """A machine bookmark, e.g. the Telegram poll offset.

    `require_user`, not `require_human`: n8n is the only caller and it has no
    browser. It reads this at the top of every poll so the offset survives what
    `$getWorkflowStaticData` does not — a workflow push, which wipes staticData
    and makes Telegram re-send a day of updates into the dedupe.
    """
    try:
        return {"name": name, "value": logs.get_cursor(name)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/cursor/{name}", responses={502: {"description": "Log store unreachable"}})
def write_cursor(name: str, payload: CursorIn,
                 caller: dict = Depends(auth.require_user)) -> dict:
    """Move a bookmark forward; a lower value is ignored, not written."""
    try:
        logs.set_cursor(name, payload.value)
        return {"name": name, "value": logs.get_cursor(name)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/message-queue", responses={502: {"description": "Log store unreachable"}})
def list_message_queue(
    limit: int = Query(50, ge=1, le=200), caller: dict = Depends(auth.require_user)
) -> dict:
    """Messages parked before they ever became a report.

    The companion of /sheet-queue, one stage earlier: that one holds a finished
    report Google refused, this one holds a message the model could not read.
    Abandoned rows are included for the same reason — the row that stopped being
    retried is the one an operator has to act on, and hiding it makes a lost
    report look like an empty queue.
    """
    try:
        return {
            "pending": logs.list_message_queue(limit),
            "max_attempts": logs.MAX_MESSAGE_ATTEMPTS,
            # Set while the text chain is refusing on quota: the queue is not
            # stuck, it is waiting, and the panel has to be able to say which.
            "paused_until": jobs.message_quota_pause(),
        }
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/sheet-queue", responses={502: {"description": "Log store unreachable"}})
def list_queue(
    limit: int = Query(20, ge=1, le=500), caller: dict = Depends(auth.require_user)
) -> dict:
    try:
        # The dashboard sees retired rows too: a payload that stopped being
        # retried is the one an operator has to act on, and hiding it is how a
        # lost report looks like an empty queue.
        return {
            "pending": logs.pending_writes(limit, include_retired=True),
            "max_attempts": logs.MAX_WRITE_ATTEMPTS,
            # Set while Google is refusing on quota: the queue is not stuck,
            # it is waiting, and the panel must be able to say which.
            "paused_until": jobs.sheet_queue_pause(),
        }
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


# ── Notifications + tasks (the bell and the to-do panel) ───────────────────
# Notifications are strictly per-account rows; the API never broadcasts to
# everybody at once. The task list is the opposite: one shared list, every
# account can edit it, and the scheduler's reminders job rings every bell.


class NotificationReadIn(BaseModel):
    ids: Optional[List[int]] = Field(
        default=None, description="Which notifications to mark read; omit for all"
    )


@app.get("/notifications", responses={502: {"description": "Log store unreachable"}})
def list_notifications(
    limit: int = Query(50, ge=1, le=500), caller: dict = Depends(auth.require_human)
) -> dict:
    try:
        return {
            "items": logs.list_notifications(caller["id"], limit),
            "unread": logs.unread_notifications(caller["id"]),
        }
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/notifications/read", responses={502: {"description": "Log store unreachable"}})
def read_notifications(payload: NotificationReadIn, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"marked": logs.mark_notifications_read(caller["id"], payload.ids)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}
_REPEAT_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def _lead_period_error(remind_value, remind_unit, repeat, repeat_every, repeat_unit):
    """A lead as long as the repeat period makes consecutive windows overlap
    (the next reminder would be due the moment the previous one fired), which
    the once-per-occurrence guard then re-fires every tick. The period is the
    custom interval when one is set, else the preset; a one-shot task accepts
    any lead. Returns the rejection message or None."""
    recurring = (repeat not in (None, "none")) or repeat_unit is not None
    if not remind_value or not recurring:
        return None
    if repeat_unit:
        period_days = repeat_every * _UNIT_DAYS[repeat_unit]
    else:
        assert repeat not in (None, "none")
        period_days = _REPEAT_DAYS[repeat]
    if _UNIT_DAYS[remind_unit] * remind_value >= period_days:
        return "le rappel avant doit être plus court que la période de répétition"
    return None


class TaskIn(BaseModel):
    title: str
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    repeat: Literal["none", "daily", "weekly", "monthly"] = "none"
    remind_before_value: Optional[int] = Field(default=None, ge=0)
    remind_before_unit: Optional[Literal["day", "week", "month"]] = None
    repeat_every: Optional[int] = Field(default=None, ge=1)
    repeat_unit: Optional[Literal["day", "week", "month"]] = None

    @model_validator(mode="after")
    def _task_pairs(self):
        if (self.remind_before_value is None) != (self.remind_before_unit is None):
            raise ValueError("remind_before_value et remind_before_unit vont ensemble")
        if (self.repeat_every is None) != (self.repeat_unit is None):
            raise ValueError("repeat_every et repeat_unit vont ensemble")
        error = _lead_period_error(self.remind_before_value, self.remind_before_unit,
                                   self.repeat, self.repeat_every, self.repeat_unit)
        if error:
            raise ValueError(error)
        return self


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    repeat: Optional[Literal["none", "daily", "weekly", "monthly"]] = None
    remind_before_value: Optional[int] = Field(default=None, ge=0)
    remind_before_unit: Optional[Literal["day", "week", "month"]] = None
    repeat_every: Optional[int] = Field(default=None, ge=1)
    repeat_unit: Optional[Literal["day", "week", "month"]] = None
    done: Optional[bool] = None

    @model_validator(mode="after")
    def _task_pairs(self):
        if (self.remind_before_value is None) != (self.remind_before_unit is None):
            raise ValueError("remind_before_value et remind_before_unit vont ensemble")
        if (self.repeat_every is None) != (self.repeat_unit is None):
            raise ValueError("repeat_every et repeat_unit vont ensemble")
        # Same overlap guard, but only when the patch itself carries the
        # repeat: otherwise the stored cadence is invisible at validation time.
        error = _lead_period_error(self.remind_before_value, self.remind_before_unit,
                                   self.repeat, self.repeat_every, self.repeat_unit)
        if error:
            raise ValueError(error)
        return self


@app.get("/tasks", responses={502: {"description": "Log store unreachable"}})
def list_tasks(caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"tasks": logs.list_tasks()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/tasks", responses={502: {"description": "Log store unreachable"}})
def create_task(payload: TaskIn, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        task_id = logs.create_task(
            payload.title, payload.notes, payload.due_at, payload.repeat,
            payload.remind_before_value, payload.remind_before_unit,
            payload.repeat_every, payload.repeat_unit,
        )
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "task_created", target=str(task_id), detail={"title": payload.title})
    return {"id": task_id, "title": payload.title, "notes": payload.notes,
            "due_at": payload.due_at, "repeat": payload.repeat,
            "remind_before_value": payload.remind_before_value,
            "remind_before_unit": payload.remind_before_unit,
            "repeat_every": payload.repeat_every, "repeat_unit": payload.repeat_unit,
            "done": False}


@app.patch("/tasks/{task_id}",
           responses={404: {"description": "Unknown task"},
                      422: {"description": "Reminder lead overlaps the repeat period"},
                      502: {"description": "Log store unreachable"}})
def update_task(task_id: int, payload: TaskPatchIn, caller: dict = Depends(auth.require_human)) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    # When the patch changes the lead but carries no repeat, the validator
    # could not see the stored cadence — and a lead as long as the stored
    # period would overlap windows and silently kill every future reminder.
    # Check the resulting state against the stored task before writing.
    if "remind_before_value" in fields and "repeat" not in fields:
        try:
            stored = logs.get_task(task_id)
        except logs.LogStoreError as exc:
            raise HTTPException(502, str(exc)) from exc
        if stored is None:
            raise HTTPException(404, TASK_NOT_FOUND)
        error = _lead_period_error(
            payload.remind_before_value, payload.remind_before_unit,
            stored["repeat"], stored["repeat_every"], stored["repeat_unit"],
        )
        if error:
            raise HTTPException(422, error)
    try:
        updated = logs.update_task(task_id, fields)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not updated:
        raise HTTPException(404, TASK_NOT_FOUND)
    auth.record(caller, "task_updated", target=str(task_id), detail=fields)
    return {"ok": True, "id": task_id}


@app.delete("/tasks/{task_id}",
            responses={404: {"description": "Unknown task"}, 502: {"description": "Log store unreachable"}})
def delete_task(task_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        deleted = logs.delete_task(task_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, TASK_NOT_FOUND)
    auth.record(caller, "task_deleted", target=str(task_id))
    return {"ok": True}


# ── Scheduled jobs ─────────────────────────────────────────────────────────
# The three cron bands that used to live in n8n. The scheduler runs them; these
# two routes are how the dashboard sees and forces them.


@app.get("/jobs")
def list_jobs(caller: dict = Depends(auth.require_human)) -> dict:
    return {"jobs": jobs.status()}


@app.post("/jobs/{name}/run", responses={404: {"description": "Unknown job"}})
async def run_job(name: str, caller: dict = Depends(auth.require_human)) -> dict:
    """Run one job now. Never 500s on a job failure — the outcome is the payload.

    Off the event loop: these read the Sheet and call models, and a synchronous
    handler would freeze every other request for the duration.
    """
    if name not in jobs.JOBS:
        raise HTTPException(404, f"unknown job: {name}")
    auth.record(caller, "job_run", target=name)
    return await run_in_threadpool(jobs.run, name)


# ── n8n orchestrator, read-only ────────────────────────────────────────────
# The dashboard's Automation panels used to call n8n straight through the Vite
# dev proxy, which attached X-N8N-API-KEY server-side. A static build has no dev
# server, so the proxy had to move -- and it moves *here* rather than into nginx
# because nginx cannot tell a logged-in browser from a stranger. Injecting the
# key in the proxy would publish a fully authenticated n8n admin API (workflows,
# credentials) to anyone who can reach the public URL.
#
# Read-only on purpose: the dashboard only ever lists. Nothing here can start,
# edit or deactivate a workflow.


async def _n8n_get(path: str) -> Any:
    """One authenticated GET against n8n's public API.

    Errors are raised as 502 and translated by the callers into the "n8n is
    unreachable" state the panels already know how to render -- an orchestrator
    that is down is a state to display, not an exception to leak.
    """
    if not settings.n8n_api_key:
        raise HTTPException(502, "N8N_API_KEY is not configured")
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.get(
                f"{settings.n8n_url.rstrip('/')}/api/v1/{path}",
                headers={"X-N8N-API-KEY": settings.n8n_api_key},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"n8n unreachable: {exc}") from exc
    if res.status_code in (401, 403):
        raise HTTPException(502, "n8n rejected the API key")
    if res.status_code >= 400:
        raise HTTPException(502, f"n8n returned {res.status_code}")
    return res.json()


@app.get("/n8n/workflows", responses={502: {"description": "n8n unreachable or misconfigured"}})
async def n8n_workflows(caller: dict = Depends(auth.require_human)) -> Any:
    return await _n8n_get("workflows")


@app.get("/n8n/executions", responses={502: {"description": "n8n unreachable or misconfigured"}})
async def n8n_executions(
    limit: int = Query(20, ge=1, le=250), caller: dict = Depends(auth.require_human)
) -> Any:
    return await _n8n_get(f"executions?limit={int(limit)}")


@app.get("/n8n/listening", responses={502: {"description": "n8n unreachable or misconfigured"}})
async def n8n_listening(caller: dict = Depends(auth.require_user)) -> dict:
    """Is the orchestrator still *listening*, not merely running?

    A reachable n8n with an active workflow proves neither: on 2026-08-19 the
    crons were unregistered mid-run and both receptions went silent for an hour
    while every status said healthy. The only honest evidence is work — the
    timestamp of the last execution, compared against how often one is expected.
    """
    body = await _n8n_get("executions?limit=1")
    items = (body or {}).get("data") or []
    last = (items[0] or {}).get("stoppedAt") or (items[0] or {}).get("startedAt") if items else None
    threshold = max(1, settings.n8n_stale_after_minutes) * 60
    age = None
    if last:
        try:
            seen = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            age = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
        except (ValueError, TypeError):
            # Unparseable, or parsed without a timezone (naive minus aware is a
            # TypeError). Neither is evidence of freshness. Left as
            # None, which reads as stale below rather than as healthy.
            age = None
    return {
        "last_execution_at": last,
        "age_seconds": age,
        "threshold_seconds": threshold,
        # No execution at all, an unreadable date, or one older than the
        # window: all three mean nothing has been heard from, and none of them
        # may be reported as listening.
        "stale": age is None or age > threshold,
    }


# ── Technician directory ───────────────────────────────────────────────────
# Managed from the dashboard, read by the reception workflow to authorize a
# sender before any transcription happens.


class TechnicianIn(BaseModel):
    channel: str = Field(..., description="telegram | whatsapp")
    external_id: str = Field(..., description="Telegram chat id or WhatsApp number")
    name: str
    role: Optional[str] = None
    active: bool = True


class NewPerson(BaseModel):
    name: str
    role: str = Field("chef", description="directeur | chef | tech")


class NewManager(BaseModel):
    # Explicitly Optional: null is the real value that moves someone back to
    # the chart's unassigned column, not a missing field.
    manager_id: Optional[int] = None


@app.get("/technicians", responses={502: {"description": "Log store unreachable"}})
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


@app.post("/technicians", responses={422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
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


@app.delete("/technicians/{tech_id}", responses={502: {"description": "Log store unreachable"}})
def remove_technician(tech_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    try:
        auth.record(caller, "technician_removed", target=str(tech_id))
        return {"deleted": logs.delete_technician(tech_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/persons/{person_id}", responses={502: {"description": "Log store unreachable"}})
def remove_person(person_id: int, caller: dict = Depends(auth.require_human)) -> dict:
    """Delete a person, their identities and their memory."""
    try:
        auth.record(caller, "person_removed", target=str(person_id))
        return {"deleted": logs.delete_person(person_id)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/persons", responses={422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
def add_person(payload: NewPerson, caller: dict = Depends(auth.require_director)) -> dict:
    """The org chart's "+": a chef with no channel and no login yet.

    Director-only, like every other write that changes who is who.
    """
    try:
        person = logs.create_person(payload.name, payload.role)
        auth.record(caller, "person_added", target=payload.name, after=payload.role)
        return person
    except logs.LogStoreError as exc:
        raise HTTPException(422 if "required" in str(exc) else 502, str(exc)) from exc


@app.patch("/persons/{person_id}/manager", responses={404: {"description": "Person not found"}, 422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
def move_person(person_id: int, payload: NewManager, caller: dict = Depends(auth.require_director)) -> dict:
    """Reassign someone to a chef, or to nobody with manager_id: null."""
    try:
        if not logs.set_manager(person_id, payload.manager_id):
            raise HTTPException(404, f"no person {person_id}")
        auth.record(caller, "person_reassigned", target=str(person_id),
                    after=str(payload.manager_id))
        return {"id": person_id, "manager_id": payload.manager_id}
    except logs.LogStoreError as exc:
        raise HTTPException(422 if "themselves" in str(exc) else 502, str(exc)) from exc


# ── Chantiers, routing and the bordereau ───────────────────────────────────
# A site is a real entity: it owns a journal tab and a contract quantity list.
# It does NOT own a crew — nobody is assigned to a site. Which site a report
# belongs to is decided per message (`journal.resolve_site`): the name the
# technician said, else the site on their own last row, else `Non affecté`.


class NewChantier(BaseModel):
    nom: str
    client: Optional[str] = None
    sheet_tab: Optional[str] = None


class NewArticle(BaseModel):
    designation: str
    unite: str = "U"
    qte_marche: Optional[float] = None
    numero: Optional[int] = None
    champ: Optional[str] = None


@app.post("/sheets/format", responses={502: {"description": "Sheets unreachable"}})
async def format_sheets(caller: dict = Depends(auth.require_director)) -> dict:
    """Re-apply the readable layout to every tab that already exists.

    New tabs are styled when they are created (`sheets.ensure_tab`), so this
    exists for the ones that predate the styling — and as the one honest way
    back if a tab is ever left looking wrong. Formatting only: it sets widths,
    freezes the header and bands the rows; it never writes, moves or reads a
    value, so running it twice is the same as running it once.

    Director-only, because it changes what the whole company sees when they
    open the file.
    """
    tabs = [sheets.RAPPORTS_TAB]
    try:
        tabs += [c["sheet_tab"] for c in logs.list_chantiers() if c.get("sheet_tab")]
    except logs.LogStoreError:
        # No chantier list is not a reason to leave Rapports unstyled.
        pass
    styled = []
    for tab in dict.fromkeys(tabs):  # de-duplicated, order kept
        await run_in_threadpool(sheets.style_tab, tab)
        styled.append(tab)
    auth.record(caller, "sheets_formatted", target=", ".join(styled))
    return {"ok": True, "tabs": styled}


@app.get("/chantiers", responses={502: {"description": "Log store unreachable"}})
def get_chantiers(active_only: bool = False, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        return {"chantiers": logs.list_chantiers(active_only)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/chantiers", responses={422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
def add_chantier(payload: NewChantier, caller: dict = Depends(auth.require_director)) -> dict:
    try:
        chantier = logs.create_chantier(payload.nom, payload.sheet_tab, payload.client)
        auth.record(caller, "chantier_added", target=payload.nom)
        return chantier
    except logs.LogStoreError as exc:
        raise HTTPException(422 if "required" in str(exc) else 502, str(exc)) from exc


@app.patch("/chantiers/{chantier_id}", responses={404: {"description": "Chantier not found"}, 502: {"description": "Log store unreachable"}})
def verify_chantier(chantier_id: int, caller: dict = Depends(auth.require_director)) -> dict:
    """Confirm a site the pipeline created from a voice note (`verifie = false`).

    Takes no body: confirming is the only edit here. The opposite of confirming
    is deleting a mis-transcription, which DELETE already does.
    """
    try:
        if not logs.verify_chantier(chantier_id):
            raise HTTPException(404, f"no chantier {chantier_id}")
        auth.record(caller, "chantier_verified", target=str(chantier_id))
        return {"id": chantier_id, "verifie": True}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/chantiers/{chantier_id}", responses={502: {"description": "Log store unreachable"}})
def remove_chantier(chantier_id: int, caller: dict = Depends(auth.require_director)) -> dict:
    """Removes the site and its bordereau. The journal tab is left alone: it is
    the director's record, and deleting a row in the dashboard must never erase
    months of reports in his file."""
    try:
        deleted = logs.delete_chantier(chantier_id)
        auth.record(caller, "chantier_removed", target=str(chantier_id))
        return {"deleted": deleted}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


# --- free articles: what the bordereau never listed ------------------------


class ArticleRename(BaseModel):
    designation: str = Field(..., min_length=1, max_length=120)


@app.get("/articles", responses={502: {"description": "Log store unreachable"}})
def list_articles(caller: dict = Depends(auth.require_user)) -> dict:
    """Articles a technician reported that no bordereau lists.

    `confirmed` false is the queue the Sites page shows: the column and its
    figures already exist — a report is never held back waiting for a human —
    so this is a review, not an approval gate.
    """
    try:
        return {"articles": logs.list_article_registry()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.patch("/articles/{slug}", responses={404: {"description": "Unknown article"}, 502: {"description": "Log store unreachable"}})
def confirm_or_rename_article(slug: str, body: Optional[ArticleRename] = None,
                              caller: dict = Depends(auth.require_director)) -> dict:
    """Accept an article as it stands, or rename it — renaming onto an existing
    name merges the two, in the registry and in every tab that carries them.

    Director-only, like confirming a site: it rewrites a column header the
    whole spreadsheet reads.
    """
    try:
        if body is None or not body.designation.strip():
            if not logs.confirm_article(slug):
                raise HTTPException(404, f"no article {slug!r}")
            auth.record(caller, "article_confirmed", slug)
            return {"ok": True, "slug": slug}
        before = next((a for a in logs.list_article_registry() if a["slug"] == slug), None)
        if before is None:
            raise HTTPException(404, f"no article {slug!r}")
        result = logs.rename_article(slug, body.designation)
        moved = sheets.rename_column(before["designation"], body.designation.strip())
        auth.record(caller, "article_renamed", slug,
                    before=before["designation"],
                    after=f"{body.designation.strip()} ({result['rows']} lignes)")
        return {"ok": True, "tabs": moved, **result}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/articles/{slug}", responses={404: {"description": "Unknown article"}, 502: {"description": "Log store unreachable"}})
def reject_article(slug: str, caller: dict = Depends(auth.require_director)) -> dict:
    """Drop a free article and its column, figures included.

    Only reachable deliberately: this is for a reading nobody recognises, and
    the numbers under it are worth less than a column named after a mistake.
    """
    try:
        dropped = logs.delete_article(slug)
        if dropped is None:
            raise HTTPException(404, f"no article {slug!r}")
        designation, rows = dropped
        removed = sheets.delete_column(designation)
        # The row count goes in the audit entry because the figures are gone
        # from `report_rows` with the column: that entry is the only place left
        # that says a total moved, and by how much of the history.
        auth.record(caller, "article_rejected", slug,
                    before=designation, after=f"{rows} lignes recalculées")
        return {"ok": True, "tabs": removed, "rows": rows}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/chantiers/{chantier_id}/bordereau", responses={404: {"description": "Chantier not found"}, 502: {"description": "Sheets or log store unreachable"}})
def get_bordereau(chantier_id: int, caller: dict = Depends(auth.require_user)) -> dict:
    """Contract quantities against what the journal actually recorded.

    `qte_installee` is computed here on every call and stored nowhere: the
    journal is the only place a quantity is entered, so a stored total could
    only ever drift from it. Articles with no `champ` have no daily counterpart
    (a switch, an onduleur) and come back with `qte_installee: null` rather than
    0 — "not tracked here" is not "none installed".
    """
    try:
        chantier = next((c for c in logs.list_chantiers() if c["id"] == chantier_id), None)
        if chantier is None:
            raise HTTPException(404, f"no chantier {chantier_id}")
        articles = logs.list_articles(chantier_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    try:
        rows = sheets.read_tab_cached(chantier["sheet_tab"])
    except sheets.SheetsError as exc:
        raise HTTPException(502, str(exc)) from exc

    totals = journal.totals(rows)
    out = []
    for article in articles:
        installed = totals.get(article["champ"]) if article.get("champ") else None
        marche = article.get("qte_marche")
        out.append({
            **article,
            "qte_installee": installed,
            "avancement": (
                round(installed / float(marche), 4)
                if installed is not None and marche not in (None, 0) else None
            ),
        })
    return {"chantier": chantier, "articles": out, "totaux": totals}


@app.get("/usage")
async def api_usage(caller: dict = Depends(auth.require_user)) -> dict:
    """How much of each free tier is left, and where each number came from.

    Off the event loop: it reads Postgres and makes one Graph API call, both
    synchronous. Never 502s — one vendor unreachable comes back as that
    provider's `error` rather than emptying the panel, because a usage page that
    disappears when Meta is slow is a page nobody trusts.
    """
    return await run_in_threadpool(usage.snapshot)


@app.get("/bots")
async def api_bots(caller: dict = Depends(auth.require_user)) -> dict:
    """The two links that open a conversation with the bot itself.

    Its own endpoint rather than a field on /usage: a reader opening a chat is
    not asking about quotas, and /usage is polled. Both values are cached for
    the process (`usage.bot_links`), so this costs a vendor round trip once per
    container. A channel that cannot be resolved comes back null — a link that
    goes nowhere is worse than no link.
    """
    return await run_in_threadpool(usage.bot_links)


@app.get("/alerts")
async def list_alerts(caller: dict = Depends(auth.require_user)) -> dict:
    """What is running out, over the contract, or about to be.

    Off the event loop: each site costs a full journal-tab read, and a
    synchronous handler would freeze every other request while Google answers.
    Findings are TTL-cached in `stock` so a dashboard poll does not turn into a
    Sheets read per site per 30 seconds.

    Never 502s. An unreadable site is skipped and printed, because a panel that
    disappears when one tab is broken looks exactly like a panel with nothing to
    report.
    """
    found = await run_in_threadpool(stock.assess)
    return {"alerts": stock.apply_mutes(found)}


class AlertMuteIn(BaseModel):
    chantier: str = Field(..., min_length=1, max_length=200)
    champ: str = Field(..., min_length=1, max_length=80)


@app.post("/alerts/mute", responses={404: {"description": "No such live alert"}, 502: {"description": "Log store unreachable"}})
async def mute_alert(body: AlertMuteIn, caller: dict = Depends(auth.require_human)) -> dict:
    """Dismiss a material finding until it gets worse.

    The level and the remainder are taken from the **server's** own assessment,
    never from the request. A client-supplied figure would let a stale tab mute
    a shortage against a number that has not been true for an hour, and the
    snapshot is the only thing standing between "ignore" and "silence forever".

    A finding that is not currently live cannot be muted: there would be
    nothing to snapshot, and the row would sit in the table pre-emptively
    hiding an alert nobody has seen yet.
    """
    found = await run_in_threadpool(stock.assess)
    live = next(
        (a for a in found if a["chantier"] == body.chantier and a["champ"] == body.champ), None
    )
    if live is None:
        raise HTTPException(404, f"no live alert for {body.champ!r} on {body.chantier!r}")
    try:
        logs.mute_alert(body.chantier, body.champ, live["niveau"], live.get("reste"),
                        caller.get("name") or caller.get("email"))
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "alert_muted", f"{body.chantier}/{body.champ}")
    return {"ok": True}


@app.delete("/alerts/mute", responses={502: {"description": "Log store unreachable"}})
def unmute_alert(chantier: str, champ: str, caller: dict = Depends(auth.require_human)) -> dict:
    """Bring a dismissed finding back for everyone."""
    try:
        removed = logs.unmute_alert(chantier, champ)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if removed:
        auth.record(caller, "alert_unmuted", f"{chantier}/{champ}")
    return {"ok": True, "removed": removed}


@app.get("/receptions", responses={502: {"description": "Log store unreachable"}})
def list_receptions(chantier: Optional[str] = None,
                    caller: dict = Depends(auth.require_user)) -> dict:
    """Material received, newest first — one site's or every site's.

    Read-only and deliberately so: a reception is declared by the message that
    carried the bon de livraison, and a second way to enter one is a second way
    for the ledger and the messages to disagree. The `Livraisons` tab mirrors
    this, and the tab is a mirror — this is the record.
    """
    try:
        return {"receptions": logs.list_receptions(chantier)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/chantiers/{chantier_id}/articles", responses={422: {"description": "Invalid input"}, 502: {"description": "Log store unreachable"}})
def add_article(chantier_id: int, payload: NewArticle,
                caller: dict = Depends(auth.require_director)) -> dict:
    try:
        article = logs.upsert_article(chantier_id, payload.designation, payload.unite,
                                      payload.qte_marche, payload.numero, payload.champ)
        auth.record(caller, "article_saved", target=payload.designation)
        return article
    except logs.LogStoreError as exc:
        raise HTTPException(422 if "required" in str(exc) else 502, str(exc)) from exc


# `/bordereau-articles/…`, not `/articles/{article_id}`: the free-article
# endpoints above claim `/articles/{slug}`, FastAPI matches the first route
# that fits, and `{slug}` fits anything — so this one had become unreachable
# the moment those were added. Two resources cannot share one path shape.
@app.delete("/bordereau-articles/{article_id}", responses={502: {"description": "Log store unreachable"}})
def remove_article(article_id: int, caller: dict = Depends(auth.require_director)) -> dict:
    try:
        deleted = logs.delete_bordereau_article(article_id)
        auth.record(caller, "article_removed", target=str(article_id))
        return {"deleted": deleted}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/persons/{person_id}/profile", responses={502: {"description": "Log store unreachable"}, 404: {"description": "Person not found"}})
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
    # The profile is built from the person's own past reports, which live in the
    # Sheet: a Google outage must surface as a 502 ("try the button again"),
    # never as a 500 that looks like our bug.
    try:
        rows = sheets.read_reports()
    except sheets.SheetsError as exc:
        raise HTTPException(502, f"sheet unreachable: {exc}") from exc
    return memory.refresh_person(person, rows)


@app.post("/profiles/refresh", responses={502: {"description": "Log store unreachable"}})
def refresh_all_profiles(caller: dict = Depends(auth.require_user)) -> dict:
    """Rebuild every profile. Called by the 03:00 cron in n8n.

    The Sheet is read once for all of them: it is the slow part, and reading it
    per technician would turn a nightly job into a quota problem of its own.
    """
    try:
        persons = logs.list_persons()
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    # Same reasoning as refresh_one_profile: the Sheet is the input, and when it
    # is down the job must say so instead of 500ing.
    try:
        rows = sheets.read_reports()
    except sheets.SheetsError as exc:
        raise HTTPException(502, f"sheet unreachable: {exc}") from exc
    results = [memory.refresh_person(p, rows) for p in persons]
    return {"refreshed": sum(1 for r in results if r["updated"]), "results": results}


@app.get("/technicians/lookup", responses={502: {"description": "Log store unreachable"}})
def lookup_technician(channel: str, external_id: str, caller: dict = Depends(auth.require_user)) -> dict:
    """Authorization check for n8n: returns the technician or `found: false`."""
    try:
        found = logs.find_technician(channel, external_id)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"found": found is not None, "technician": found}


# ── Technician replies ─────────────────────────────────────────────────────
# The inbox composer. The API sends on the technician's own channels (Telegram
# Bot API / WhatsApp Cloud API) so a manager's answer works without n8n. The
# channel tokens are optional; when unset the endpoint answers 501 loudly.


class ReplyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Technician name as written in the Sheet")
    text: str = Field(..., min_length=1, max_length=4000, description="Reply text")
    identity_id: Optional[int] = Field(
        default=None,
        description=(
            "Send on this channel identity only. Omitted, the reply goes to every "
            "active identity of the person — the behaviour before the inbox had a picker."
        ),
    )


@app.post("/reply", responses={404: {"description": "No person with that name or no active channel"}, 422: {"description": "Invalid input"}, 501: {"description": "Channel tokens not configured"}, 502: {"description": "Channel refused the message"}})
def send_reply(payload: ReplyIn, caller: dict = Depends(auth.require_human)) -> dict:
    """Send a manager's reply to a technician, on every active channel of theirs."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "text is required")
    try:
        person = logs.person_by_name(payload.name)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    if person is None:
        raise HTTPException(404, f"no technician named {payload.name!r}")
    identities = [t for t in person.get("identities", []) if t.get("active")]
    if payload.identity_id is not None:
        # Narrowed to the one the operator picked. A 404 rather than a silent
        # broadcast: sending a private answer to every number a technician owns
        # because the chosen one went inactive is worse than not sending it.
        identities = [t for t in identities if t.get("id") == payload.identity_id]
        if not identities:
            raise HTTPException(404, f"identity {payload.identity_id} is not an active channel of {payload.name}")
    if not identities:
        raise HTTPException(404, f"{payload.name} has no active channel")
    try:
        result = reply.reply_to_identities(identities, payload.text)
    except reply.ReplyError as exc:
        raise HTTPException(502, str(exc)) from exc
    auth.record(caller, "reply_sent", target=payload.name, detail=result)
    return result


# ── Operator settings ──────────────────────────────────────────────────────
# Report schedule, notification recipients and export format. Stored here so
# the dashboard and any scheduler read one source of truth.


class SettingsIn(BaseModel):
    values: Dict[str, Any]


@app.get("/stt/status")
def stt_status(days: int = 7, caller: dict = Depends(auth.require_human)) -> dict:
    """Engines, the live order, and how often each one actually served.

    Readable by any account — seeing which engine transcribed is operational
    information. Only *changing* the order is director-only (PUT /settings).

    `usage` counts wins, not attempts: an engine that failed and fell through
    contributes nothing, so a rising `local` count means the free tiers were
    unavailable. Quota is deliberately asymmetric and labelled as such — Groq
    returns rate-limit headers, Gemini exposes no quota at all, and reporting
    our own call count in a slot labelled "quota" would invent a limit that
    does not exist.
    """
    chain = [p.strip() for p in _stt_chain().split(",") if p.strip()]
    usage: dict = {"engines": [], "days": days, "error": None}
    try:
        usage = logs.stt_usage(days)
        usage["error"] = None
    except Exception as exc:  # noqa: BLE001  # the panel must render without Postgres
        usage = {"engines": [], "days": days, "error": str(exc)}

    local_state = "not_configured" if not settings.stt_local_url else "unknown"
    if settings.stt_local_url:
        try:
            import httpx

            r = httpx.get(settings.stt_local_url.rstrip("/") + "/health", timeout=3)
            local_state = r.json().get("status", "unknown") if r.status_code == 200 else "down"
        # Unreachable is a state, not an error: the sidecar being off is normal.
        except Exception:  # noqa: BLE001
            local_state = "down"

    return {
        "available": available_providers(),
        "chain": chain,
        # The .env order, so the dashboard's reset restores the benchmarked
        # default rather than a hardcoded list the frontend would have to keep
        # in sync with config.py.
        "default_chain": [p.strip() for p in settings.stt_chain.split(",") if p.strip()],
        "usage": usage,
        "local": {"url_set": bool(settings.stt_local_url), "status": local_state},
        # What the dashboard may show as a real remaining quota, versus a plain
        # count of our own calls. Keeps the UI from implying Gemini has a gauge.
        "quota_reporting": {"groq": "headers", "gemini": "none", "local": "unlimited"},
    }


@app.get("/settings", responses={502: {"description": "Log store unreachable"}})
def read_settings(caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"settings": logs.get_settings()}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put(
    "/settings",
    responses={
        403: {"description": "Only the director may reorder the STT chain"},
        422: {"description": "Unknown STT provider name"},
        502: {"description": "Log store unreachable"},
    },
)
def write_settings(payload: SettingsIn, caller: dict = Depends(auth.require_human)) -> dict:
    # The STT order decides which engine hears every voice note, so it is
    # director-only — narrower than the rest of this endpoint, which any account
    # may write. Enforced here rather than by a separate endpoint because the
    # dashboard saves the whole settings object in one PUT; a 403 on the field is
    # clearer than silently dropping it, which would look like a save that worked.
    if "stt_chain" in payload.values and caller.get("role") != "directeur":
        raise HTTPException(403, "Seul le directeur peut modifier l'ordre des moteurs STT")
    if "stt_chain" in payload.values:
        known = set(available_providers())
        asked = [p.strip() for p in str(payload.values["stt_chain"]).split(",") if p.strip()]
        unknown = [p for p in asked if p not in known]
        # Reject a typo instead of storing it: an unknown name is skipped at
        # transcription time, so "grok,gemini" would quietly run one engine short.
        if unknown or not asked:
            raise HTTPException(
                422, f"Moteurs STT inconnus: {unknown or ['(vide)']}. Disponibles: {sorted(known)}"
            )
        payload.values["stt_chain"] = ",".join(asked)
    auth.record(caller, "settings_saved", detail=payload.values)
    try:
        return {"settings": logs.put_settings(payload.values)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


# ── Per-account settings ────────────────────────────────────────────────────
# What this browser prefers: clock format, density, confidence threshold. The
# browser keeps the defaults; the database keeps what each account chose, so
# the preferences follow the person across browsers and machines instead of
# being tied to one browser's localStorage.

class MeSettingsIn(BaseModel):
    values: Dict[str, Any]


@app.get("/me/settings", responses={502: {"description": "Log store unreachable"}})
def read_me_settings(caller: dict = Depends(auth.require_human)) -> dict:
    try:
        return {"settings": logs.get_person_settings(caller["id"])}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put("/me/settings", responses={403: {"description": "Confidence is director-only"}, 502: {"description": "Log store unreachable"}})
def write_me_settings(payload: MeSettingsIn, caller: dict = Depends(auth.require_human)) -> dict:
    # The confidence threshold left the browser the day these settings became
    # server-side, so it needs a real gate now: the dashboard hides the slider
    # from non-directors, but the API must refuse the value too.
    if "confidence" in payload.values and caller.get("role") != "directeur":
        raise HTTPException(403, "le seuil de confiance est réservé au directeur")
    auth.record(caller, "settings_saved", detail=payload.values)
    try:
        return {"settings": logs.put_person_settings(caller["id"], payload.values)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class TestMailIn(BaseModel):
    to: str


@app.post("/notify/test", responses={422: {"description": "SMTP not configured"}, 502: {"description": "Mail relay error"}})
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
        # A full report with randomised figures, not one sentence: the point of
        # the probe is to show the recipient what they are subscribing to, and
        # the plain line proved delivery while showing nothing. The plain-text
        # part stays plain — it is the fallback, and it says outright that the
        # numbers are invented so nobody forwards the sample as a real day.
        subject, html = mailer.sample_report(payload.to)
        mailer.send(
            [payload.to],
            subject,
            "Ceci est un message de test envoyé depuis le tableau de bord aznet.\n"
            "Il reprend la mise en page des rapports quotidiens, avec des chiffres "
            "tirés au hasard — ce ne sont pas les données réelles de la journée.\n"
            "Si vous le recevez, l'adresse est correctement configurée pour les "
            "rapports quotidiens et hebdomadaires.",
            html_body=html,
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


@app.post("/service-samples", responses={502: {"description": "Log store unreachable"}})
def post_samples(payload: SamplesIn, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        return {"written": logs.record_samples([s.model_dump() for s in payload.samples])}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/service-samples", responses={502: {"description": "Log store unreachable"}})
def get_samples(hours: int = 1, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        return {"samples": logs.read_samples(hours)}
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc


class ResolveRequest(BaseModel):
    ok: bool
    error: Optional[str] = None


@app.patch("/sheet-queue/{write_id}", responses={502: {"description": "Log store unreachable"}})
def resolve_queue_item(write_id: int, payload: ResolveRequest, caller: dict = Depends(auth.require_user)) -> dict:
    try:
        logs.resolve_write(write_id, payload.ok, payload.error)
    except logs.LogStoreError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True}
