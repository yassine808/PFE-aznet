"""LLM extraction + French reformulation.

One prompt, three input shapes, and an explicit ordered fallback chain per
shape (`EXTRACTION_TEXT_CHAIN` / `EXTRACTION_IMAGE_CHAIN` in `config.py`):

    text   — a typed report, or an STT transcription
    image  — a photo of a notebook page, whiteboard or delivery note
    audio  — handled upstream by `app/providers/` (STT), then arrives here as text

Every chain entry is `provider:model`. The chain is tried in order and the
first success wins; if all of them fail the combined error is raised, because a
silent fallback to "no data" would put an empty row in the manager's Sheet and
look like a quiet day on the chantier.

Model choice is not taste: see `benchmark/run_model_benchmark.py` and the
results table in `benchmark/README.md`.
"""
import json
from functools import lru_cache
from typing import List, Optional, Tuple

from app import prompt_loader
from app import usage
from app.config import settings
from app.schemas import ExtractedReport, QUANTITY_FIELDS


# One SDK client per process, the same rule the three STT providers already
# follow (see providers/groq_whisper.py, gemini_audio.py, local_darija.py).
# Each client owns a keep-alive connection pool, so constructing one per call
# threw that pool away and paid a fresh TCP+TLS handshake to Google or Groq on
# every single report — and unlike transcription, extraction runs on *every*
# /process request, text and audio alike. The API-key checks stay per-call in
# _call_gemini/_call_groq, so a missing key still fails loudly and never
# reaches the cache.
@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai  # lazy: keeps the test suite dependency-free

    return genai.Client(api_key=settings.gemini_api_key)


@lru_cache(maxsize=1)
def _groq_client():
    from groq import Groq  # lazy: keeps the test suite dependency-free

    return Groq(api_key=settings.groq_api_key)


class ExtractionError(RuntimeError):
    pass


DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"


# Prompts are Markdown in app/prompts/, loaded once and cached. `_INSTRUCTIONS`
# stays exported under its old name: benchmark/run_model_benchmark.py imports it,
# and the benchmark must score exactly what production sends.
_INSTRUCTIONS = prompt_loader.load(prompt_loader.TEXT_EXTRACTION)
_IMAGE_INSTRUCTIONS = prompt_loader.load(prompt_loader.IMAGE_EXTRACTION)


def _parse_chain(raw: str) -> List[Tuple[str, str]]:
    """`"gemini:x,groq:y"` -> `[("gemini", "x"), ("groq", "y")]`."""
    entries = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        provider, _, model = item.partition(":")
        if not model:
            raise ExtractionError(f"malformed chain entry {item!r} — expected 'provider:model'")
        entries.append((provider.strip(), model.strip()))
    if not entries:
        raise ExtractionError("empty extraction chain")
    return entries


def _profile_block(profile: Optional[str]) -> str:
    """The technician's profile, framed so it cannot be read as report content.

    Explicitly labelled as context and explicitly forbidden as a source of
    values. Without that framing a profile saying "intervient surtout sur Sidi
    Maarouf" is one plausible step away from filling `chantier` on a message
    that never named a site -- which is inventing data.
    """
    if not profile or not profile.strip():
        return ""
    return (
        "\n\n## Contexte sur l'auteur (informatif)\n"
        + profile.strip()
        + "\n\nCe contexte sert uniquement à mieux comprendre sa façon de s'exprimer. "
        "Il n'est JAMAIS une source de valeurs : ne remplis aucun champ à partir de lui."
    )


def _caption_block(caption: Optional[str]) -> str:
    """The caption that came with a photo, framed as part of the message.

    Same logic as `_profile_block`: labelled as message content so the model
    reads it, and explicitly tied to the photo so it cannot float free.
    """
    if not caption or not caption.strip():
        return ""
    return (
        "\n\n## Légende envoyée avec la photo\n"
        + caption.strip()
        + "\n\nCette légende fait partie du message du technicien : elle décrit la photo. "
        "Utilise-la comme une source de valeurs, au même titre que l'image."
    )


@lru_cache(maxsize=1)
def _gemini_schema() -> dict:
    """`ExtractedReport` as a JSON schema Gemini will actually accept.

    Gemini's `response_schema` is not JSON Schema — it is a subset, and it
    rejects the whole request with a 400 when it meets a keyword outside it.
    `livraisons` is a `dict[str, float]`, which Pydantic renders with
    `additionalProperties`, so from the day deliveries shipped (2026-08-16)
    every Gemini call answered:

        Unknown name "additional_properties" at
        'generation_config.response_schema.properties[50].value'

    The text chain survived it because Groq answers second. The **image chain
    is Google-only** — there is no free vision model at Groq — so all three
    engines failed on the identical malformed request, and from the outside
    that reads exactly like an account-wide quota. It is not: it is a 400, on
    every call, regardless of usage.

    Stripped rather than restructured: turning `livraisons` into a list of
    objects would change the contract with n8n, the prompts and the journal to
    work around a limitation in one vendor's parser. The keyword only says
    "values are numbers", which the prompt states anyway, so dropping it costs
    nothing — and the response is validated against the real model on the way
    back in, where it actually matters.
    """
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in ("additionalProperties", "$defs")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(ExtractedReport.model_json_schema())


def _call_gemini(
    model: str,
    text: Optional[str] = None,
    image: Optional[bytes] = None,
    mime_type: str = DEFAULT_IMAGE_MIME_TYPE,
    profile: Optional[str] = None,
    caption: Optional[str] = None,
) -> ExtractedReport:
    if not settings.gemini_api_key:
        raise ExtractionError("GEMINI_API_KEY not configured")
    from google.genai import types

    client = _gemini_client()
    if image is not None:
        contents = [types.Part.from_bytes(data=image, mime_type=mime_type),
                    _IMAGE_INSTRUCTIONS + _caption_block(caption) + _profile_block(profile)]
    else:
        contents = _INSTRUCTIONS + _profile_block(profile) + "\n\n" + (text or "")
    try:
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config={"response_mime_type": "application/json",
                    "response_schema": _gemini_schema()},
        )
        usage.from_gemini(resp, model, "extraction")
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"gemini/{model}: {exc}") from exc
    # Validated here rather than by the SDK: a dict schema makes `resp.parsed`
    # a plain dict, and the model is the contract — an answer that does not fit
    # it has to fail loudly on this engine so the chain moves to the next one.
    try:
        return ExtractedReport.model_validate_json(resp.text or "")
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(
            f"gemini/{model}: unparseable response {resp.text!r:.200} ({exc})"
        ) from exc


def _call_groq(
    model: str,
    text: Optional[str] = None,
    image: Optional[bytes] = None,
    mime_type: str = DEFAULT_IMAGE_MIME_TYPE,
    profile: Optional[str] = None,
    caption: Optional[str] = None,
) -> ExtractedReport:
    if image is not None:
        # Checked live against GET /models: the free Groq catalogue is text and
        # audio only. Saying so here beats a confusing 400 from the API.
        raise ExtractionError(f"groq/{model}: no vision model in the free catalogue")
    if not settings.groq_api_key:
        raise ExtractionError("GROQ_API_KEY not configured")
    client = _groq_client()
    schema_hint = json.dumps(
        {k: v.get("type", "string") for k, v in ExtractedReport.model_json_schema()["properties"].items()},
        ensure_ascii=False,
    )
    try:
        # `with_raw_response` rather than `create`: the parsed body drops the
        # headers, and Groq's headers are the only live quota reading any vendor
        # here gives us. `usage.from_groq` unwraps it back to the completion.
        resp = usage.from_groq(client.chat.completions.with_raw_response.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                # The profile belongs here, not only in _call_gemini: groq is the
                # *primary* text engine, so leaving it out meant the nightly
                # profile was built, stored, read and then silently dropped on
                # every normal request. `caption` stays out on purpose — it only
                # arrives with an image, which this engine refused above.
                {"role": "system", "content": _INSTRUCTIONS + _profile_block(profile)
                 + f"\nRéponds en JSON avec exactement ces clés: {schema_hint}"},
                {"role": "user", "content": text or ""},
            ],
        ), model, "extraction")
        raw = resp.choices[0].message.content
        if not raw:
            raise ValueError("empty completion")
        return ExtractedReport.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001
        # A refusal is the only place Groq states its *daily* ceiling — the
        # headers carry the per-minute window and nothing else, so without this
        # the usage page reports a comfortable minute while the day is spent,
        # which is exactly how the pipeline lost its articles on 2026-08-19
        # with every panel showing green.
        usage.note_quota_refusal("groq", model, "extraction", exc)
        raise ExtractionError(f"groq/{model}: {exc}") from exc


_ENGINES = {"gemini": _call_gemini, "groq": _call_groq}


def _carries_figures(report: ExtractedReport) -> bool:
    """Did this extraction come back with any *number*, or only with labels?

    `has_data()` is the wrong test for the chain, and a live message proved it:
    Gemini returned `equipe` and `etages` and nothing else — both in
    `DATA_FIELDS`, so `has_data()` said yes — while the message listed six
    articles with their counts. A correct answer from another engine was never
    asked for, because something had come back.

    Names and floors are what a model gets right when it has stopped reading.
    Quantities are the part that is expensive to extract and the part the
    journal exists for, so the chain judges on those.
    """
    if report.articles_libres or report.livraisons:
        return True
    return any(getattr(report, f, None) is not None for f in QUANTITY_FIELDS)


def _run_chain(
    chain: str,
    text: Optional[str] = None,
    image: Optional[bytes] = None,
    mime_type: str = DEFAULT_IMAGE_MIME_TYPE,
    profile: Optional[str] = None,
    caption: Optional[str] = None,
) -> Tuple[ExtractedReport, str]:
    """Try each `provider:model` in order. Returns (report, winning model id)."""
    failures: List[str] = []
    empty: Optional[Tuple[ExtractedReport, str]] = None
    for provider, model in _parse_chain(chain):
        engine = _ENGINES.get(provider)
        if engine is None:
            failures.append(f"{provider}: unknown provider")
            continue
        try:
            report = engine(model, text=text, image=image, mime_type=mime_type,
                            profile=profile, caption=caption)
        except ExtractionError as exc:
            failures.append(str(exc))
            continue
        # An engine that answers with nothing is not an engine that answered.
        #
        # The chain moves on when a call *fails*; it cannot move on when a model
        # returns a well-formed empty object with a 200. On 2026-08-19 that cost
        # a whole report: a message listing forty items across eight article
        # types came back from Gemini with every quantity null, so the one model
        # that could read it was never asked. The report was filed empty and
        # nothing anywhere said so.
        #
        # The test is deliberately narrow. Digits in the message and no data
        # extracted is a weak model far more often than it is a real report —
        # "salam" carries no digits and is unaffected, which is the case
        # `has_data` was written for. The fallback is kept, not discarded: if
        # every engine answers this way the first answer still stands, because
        # losing a report to a heuristic would be worse than the emptiness it
        # was trying to catch.
        if text and not _carries_figures(report) and any(c.isdigit() for c in text):
            failures.append(f"{provider}/{model}: no data extracted from a message with figures")
            empty = empty or (report, f"{provider}/{model}")
            continue
        return report, f"{provider}/{model}"
    if empty:
        return empty
    raise ExtractionError("extraction failed on every engine — " + " | ".join(failures))


def extract_report(text: str) -> ExtractedReport:
    """Text path. Signature kept single-argument: n8n and the tests both rely on it."""
    report, _ = _run_chain(settings.extraction_text_chain, text=text)
    return report


def extract_report_with_model(text: str, profile: Optional[str] = None) -> Tuple[ExtractedReport, str]:
    """Same as `extract_report` but also reports which model answered.

    `profile` is the nightly summary of the technician who sent this (see
    app/memory.py); it is optional so an unknown sender, or a Sheets outage,
    degrades to exactly the previous behaviour rather than failing.
    """
    return _run_chain(settings.extraction_text_chain, text=text, profile=profile)


def extract_report_from_image(
    image: bytes,
    mime_type: str = DEFAULT_IMAGE_MIME_TYPE,
    profile: Optional[str] = None,
    caption: Optional[str] = None,
) -> Tuple[ExtractedReport, str]:
    """Vision path — a photographed note or a picture of the work itself.

    `caption` is the text sent alongside the photo (Telegram captions); it is
    fed to the model as part of the message.
    """
    return _run_chain(
        settings.extraction_image_chain, image=image, mime_type=mime_type, profile=profile, caption=caption
    )
