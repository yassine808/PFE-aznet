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

from app.config import settings
from app.schemas import ExtractedReport


class ExtractionError(RuntimeError):
    pass


_INSTRUCTIONS = """Tu analyses le rapport journalier d'un technicien de câblage réseau au Maroc.
Le texte peut être en darija (arabe marocain), en français, ou mélangé, et provient
souvent d'une transcription vocale imparfaite (corrige mentalement les erreurs évidentes
grâce au contexte métier : goulotte, câble réseau, panneau de brassage, prise RJ45, baie,
bureau, étage, chantier).

Extrais les informations suivantes. Règles strictes :
- Convertis les nombres énoncés en lettres (arabe ou français) en chiffres.
- Les quantités sont en mètres pour goulottes et câbles.
- Si une information est absente du texte, mets null. N'invente JAMAIS.
- Si le technicien se corrige ("300... non, 350"), retiens la dernière valeur.
- Un nombre collé à autre chose qu'une quantité (étage, numéro de bureau, effectif)
  n'est pas une quantité : laisse le champ concerné à null.
- "autres_travaux" : travaux réels mentionnés qui ne rentrent dans aucune quantité standard.
- "observations" : problèmes, manques de matériel, remarques.
- "resume" : 2 à 4 phrases en français professionnel, à la 3e personne, style compte rendu
  destiné au chef de chantier. Toujours rempli.

Rapport du technicien :
"""

_IMAGE_INSTRUCTIONS = (
    "Cette image est une photo prise par un technicien de câblage : page de carnet, "
    "tableau blanc, bon de livraison, ou vue du chantier. Lis tout le texte visible "
    "(français, darija en lettres latines, ou arabe) et décris aussi ce que montre la "
    "photo si elle contient du travail réalisé. Puis extrais le rapport.\n"
    "Si l'image ne contient aucune information exploitable, mets tous les champs à null "
    "et explique-le dans \"resume\".\n\n"
) + _INSTRUCTIONS


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


def _call_gemini(
    model: str,
    text: Optional[str] = None,
    image: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
) -> ExtractedReport:
    if not settings.gemini_api_key:
        raise ExtractionError("GEMINI_API_KEY not configured")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    if image is not None:
        contents = [types.Part.from_bytes(data=image, mime_type=mime_type), _IMAGE_INSTRUCTIONS]
    else:
        contents = _INSTRUCTIONS + (text or "")
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
    mime_type: str = "image/jpeg",
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
                {"role": "system", "content": _INSTRUCTIONS + f"\nRéponds en JSON avec exactement ces clés: {schema_hint}"},
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
    mime_type: str = "image/jpeg",
) -> Tuple[ExtractedReport, str]:
    """Try each `provider:model` in order. Returns (report, winning model id)."""
    failures = []
    for provider, model in _parse_chain(chain):
        engine = _ENGINES.get(provider)
        if engine is None:
            failures.append(f"{provider}: unknown provider")
            continue
        try:
            return engine(model, text=text, image=image, mime_type=mime_type), f"{provider}/{model}"
        except ExtractionError as exc:
            failures.append(str(exc))
    raise ExtractionError("extraction failed on every engine — " + " | ".join(failures))


def extract_report(text: str) -> ExtractedReport:
    """Text path. Signature kept single-argument: n8n and the tests both rely on it."""
    report, _ = _run_chain(settings.extraction_text_chain, text=text)
    return report


def extract_report_with_model(text: str) -> Tuple[ExtractedReport, str]:
    """Same as `extract_report` but also reports which model answered."""
    return _run_chain(settings.extraction_text_chain, text=text)


def extract_report_from_image(image: bytes, mime_type: str = "image/jpeg") -> Tuple[ExtractedReport, str]:
    """Vision path — a photographed note or a picture of the work itself."""
    return _run_chain(settings.extraction_image_chain, image=image, mime_type=mime_type)
