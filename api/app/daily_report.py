"""End-of-day rollup: today's report rows → one professional French email.

Same engine strategy as extraction.py — Gemini structured output primary,
Groq Llama JSON-mode fallback, both failing raises a combined error.
n8n's daily cron collects the day's Sheet rows and calls /daily-report;
this module only turns rows into email-ready content.
"""
import json
from typing import List

from pydantic import BaseModel, Field

from app.config import settings


class DailyReportError(RuntimeError):
    pass


class DailyReportContent(BaseModel):
    """LLM output — subject + body of the end-of-day manager email."""

    objet: str = Field(..., description="Objet de l'email (une ligne, avec la date)")
    corps: str = Field(
        ...,
        description=(
            "Corps de l'email en français professionnel : synthèse de la journée, "
            "puis un point par technicien/chantier, puis problèmes signalés."
        ),
    )


_INSTRUCTIONS = """Tu rédiges le rapport de fin de journée destiné au directeur d'une société
de câblage réseau au Maroc, à partir des rapports individuels des techniciens ci-dessous
(déjà structurés). Règles :
- Français professionnel, ton compte rendu, 3e personne.
- Commence par une synthèse chiffrée de la journée (totaux : goulottes, câbles,
  bureaux terminés, panneaux raccordés) uniquement à partir des chiffres fournis.
- Ensuite un court paragraphe ou point par chantier/technicien.
- Termine par les problèmes et besoins matériels signalés ("observations"), s'il y en a.
- N'invente JAMAIS de chiffre ni d'information absente des rapports.
- "objet" : une ligne du type "Rapport journalier — <date> — <n> intervention(s)".

Date du jour : {date}
Rapports du jour (JSON) :
"""


def _generate_gemini(date: str, rows_json: str) -> DailyReportContent:
    if not settings.gemini_api_key:
        raise DailyReportError("GEMINI_API_KEY not configured")
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=_INSTRUCTIONS.format(date=date) + rows_json,
            config={
                "response_mime_type": "application/json",
                "response_schema": DailyReportContent,
            },
        )
        parsed = resp.parsed
    except Exception as exc:  # noqa: BLE001
        raise DailyReportError(f"gemini: {exc}") from exc
    if not isinstance(parsed, DailyReportContent):
        raise DailyReportError(f"gemini: unparseable response {resp.text!r:.200}")
    return parsed


def _generate_groq(date: str, rows_json: str) -> DailyReportContent:
    if not settings.groq_api_key:
        raise DailyReportError("GROQ_API_KEY not configured")
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.groq_llm_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": _INSTRUCTIONS.format(date=date)
                    + '\nRéponds en JSON avec exactement ces clés: {"objet": "...", "corps": "..."}',
                },
                {"role": "user", "content": rows_json},
            ],
        )
        raw = resp.choices[0].message.content
        return DailyReportContent.model_validate_json(raw)
    except DailyReportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DailyReportError(f"groq: {exc}") from exc


def generate_daily_report(date: str, rows: List[dict]) -> DailyReportContent:
    """Primary engine with explicit fallback — never silent (both failures raise)."""
    rows_json = json.dumps(rows, ensure_ascii=False)
    try:
        return _generate_gemini(date, rows_json)
    except DailyReportError as primary_err:
        try:
            return _generate_groq(date, rows_json)
        except DailyReportError as fallback_err:
            raise DailyReportError(
                f"daily report failed on both engines — gemini: {primary_err} | groq: {fallback_err}"
            ) from fallback_err
