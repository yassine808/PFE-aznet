"""LLM extraction + French reformulation.

Primary: Gemini 2.5 Flash structured output (response_schema = ExtractedReport).
Fallback: Groq Llama 3.3 in JSON mode. Both free tier. Prompt embeds chantier
domain vocabulary so the LLM also repairs plausible STT errors in context.
"""
import json

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
- "autres_travaux" : travaux réels mentionnés qui ne rentrent dans aucune quantité standard.
- "observations" : problèmes, manques de matériel, remarques.
- "resume" : 2 à 4 phrases en français professionnel, à la 3e personne, style compte rendu
  destiné au chef de chantier. Toujours rempli.

Rapport du technicien :
"""


def _extract_gemini(text: str) -> ExtractedReport:
    if not settings.gemini_api_key:
        raise ExtractionError("GEMINI_API_KEY not configured")
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=_INSTRUCTIONS + text,
            config={
                "response_mime_type": "application/json",
                "response_schema": ExtractedReport,
            },
        )
        parsed = resp.parsed
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"gemini: {exc}") from exc
    if not isinstance(parsed, ExtractedReport):
        raise ExtractionError(f"gemini: unparseable response {resp.text!r:.200}")
    return parsed


def _extract_groq(text: str) -> ExtractedReport:
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
            model=settings.groq_llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _INSTRUCTIONS + f"\nRéponds en JSON avec exactement ces clés: {schema_hint}"},
                {"role": "user", "content": text},
            ],
        )
        raw = resp.choices[0].message.content
        return ExtractedReport.model_validate_json(raw)
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"groq: {exc}") from exc


def extract_report(text: str) -> ExtractedReport:
    """Primary engine with explicit fallback — never silent (both failures raise)."""
    try:
        return _extract_gemini(text)
    except ExtractionError as primary_err:
        try:
            return _extract_groq(text)
        except ExtractionError as fallback_err:
            raise ExtractionError(
                f"extraction failed on both engines — gemini: {primary_err} | groq: {fallback_err}"
            ) from fallback_err
