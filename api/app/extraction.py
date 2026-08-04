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
from typing import List, Optional, Tuple

from app import prompt_loader
from app.config import settings
from app.schemas import ExtractedReport


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
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    if image is not None:
        contents = [types.Part.from_bytes(data=image, mime_type=mime_type),
                    _IMAGE_INSTRUCTIONS + _caption_block(caption) + _profile_block(profile)]
    else:
        contents = _INSTRUCTIONS + _profile_block(profile) + "\n\n" + (text or "")
    try:
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config={"response_mime_type": "application/json", "response_schema": ExtractedReport},
        )
        parsed = resp.parsed
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"gemini/{model}: {exc}") from exc
    if not isinstance(parsed, ExtractedReport):
        raise ExtractionError(f"gemini/{model}: unparseable response {resp.text!r:.200}")
    return parsed


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
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    schema_hint = json.dumps(
        {k: v.get("type", "string") for k, v in ExtractedReport.model_json_schema()["properties"].items()},
        ensure_ascii=False,
    )
    try:
        resp = client.chat.completions.create(
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
        )
        return ExtractedReport.model_validate_json(resp.choices[0].message.content)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"groq/{model}: {exc}") from exc


_ENGINES = {"gemini": _call_gemini, "groq": _call_groq}


def _run_chain(
    chain: str,
    text: Optional[str] = None,
    image: Optional[bytes] = None,
    mime_type: str = DEFAULT_IMAGE_MIME_TYPE,
    profile: Optional[str] = None,
    caption: Optional[str] = None,
) -> Tuple[ExtractedReport, str]:
    """Try each `provider:model` in order. Returns (report, winning model id)."""
    failures = []
    for provider, model in _parse_chain(chain):
        engine = _ENGINES.get(provider)
        if engine is None:
            failures.append(f"{provider}: unknown provider")
            continue
        try:
            return (engine(model, text=text, image=image, mime_type=mime_type, profile=profile, caption=caption),
                    f"{provider}/{model}")
        except ExtractionError as exc:
            failures.append(str(exc))
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
