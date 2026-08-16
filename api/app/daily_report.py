"""End-of-day rollup: today's report rows → one professional French email.

Same engine strategy as extraction.py — Gemini structured output primary,
Groq Llama JSON-mode fallback, both failing raises a combined error.
n8n's daily cron collects the day's Sheet rows and calls /daily-report;
this module only turns rows into email-ready content.
"""
import json
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field

from app import usage
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
(déjà structurés).

STRUCTURE OBLIGATOIRE du champ "corps" — exactement les sections listées
ci-dessous, dans cet ordre, chaque titre sur sa propre ligne et préfixé de "## " :

## Synthèse
Un paragraphe court : nombre d'interventions, techniciens mobilisés, chantiers
couverts, et les quantités du bloc TOTAUX. Reprends ces totaux tels quels — ils
sont déjà calculés, ne les recalcule pas et n'en invente aucun autre.

## Détail par chantier
Une puce par chantier (ou par technicien si le chantier n'est pas renseigné),
commençant par "- ", au format : "- <Chantier> — <technicien> : <ce qui a été fait,
avec les quantités de ce chantier>".

## Problèmes et besoins
Une puce par problème, arrêt de chantier ou besoin matériel signalé — champs
"observations", "motif_arret" (avec "arrets_min" s'il est renseigné) et "besoins".
S'il n'y en a aucun, écrire exactement : "- Aucun problème signalé."
{alertes}
## Prochaines étapes
Une puce par suite annoncée (champ "prochaines_etapes"), préfixée du chantier
concerné. S'il n'y en a aucune, écrire exactement : "- Aucune étape annoncée."

Règles de rédaction :
- Français professionnel, ton compte rendu, 3e personne.
- N'invente JAMAIS un chiffre ni une information absente des rapports.
- Pas de formule de politesse d'ouverture ni de clôture, pas de mots de remplissage
  (« veuillez », « n'hésitez pas », « bien sûr ») : le directeur lit ce rapport
  d'affilée avec d'autres.
- Aucun autre titre que ceux ci-dessus, et aucun gras Markdown : les titres
  "## " sont le seul balisage, parce qu'ils sont convertis en vrais styles Word.
- "objet" : une ligne. **Le mot dépend de la période fournie ci-dessous** —
  une seule journée donne "Rapport journalier — <date> — <n> intervention(s)",
  un intervalle (deux dates séparées par une flèche) donne
  "Rapport hebdomadaire — <début> au <fin> — <n> intervention(s)". Un rapport
  couvrant sept jours et intitulé « journalier » est lu comme celui de la
  veille, et le lecteur croit avoir déjà vu le reste.

Période couverte : {date}
"""


# One SDK client per process — the rule extraction.py and the STT providers
# follow. The report jobs call this once for the company digest and once per
# chef, so a client per call meant a fresh TLS handshake per manager, twice a
# day. The key checks stay in the callers, so a missing key still fails loudly
# and never reaches the cache.
@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai  # lazy: keeps the test suite dependency-free

    return genai.Client(api_key=settings.gemini_api_key)


@lru_cache(maxsize=1)
def _groq_client():
    from groq import Groq  # lazy: keeps the test suite dependency-free

    return Groq(api_key=settings.groq_api_key)


def _generate_gemini(date: str, rows_json: str, alertes: str = "") -> DailyReportContent:
    if not settings.gemini_api_key:
        raise DailyReportError("GEMINI_API_KEY not configured")
    try:
        resp = _gemini_client().models.generate_content(
            model=settings.gemini_model,
            contents=_INSTRUCTIONS.format(date=date, alertes=alertes) + rows_json,
            config={
                "response_mime_type": "application/json",
                "response_schema": DailyReportContent,
            },
        )
        usage.from_gemini(resp, settings.gemini_model, "report")
        parsed = resp.parsed
    except Exception as exc:  # noqa: BLE001
        raise DailyReportError(f"gemini: {exc}") from exc
    if not isinstance(parsed, DailyReportContent):
        raise DailyReportError(f"gemini: unparseable response {resp.text!r:.200}")
    return parsed


def _generate_groq(date: str, rows_json: str, alertes: str = "") -> DailyReportContent:
    if not settings.groq_api_key:
        raise DailyReportError("GROQ_API_KEY not configured")
    try:
        resp = usage.from_groq(_groq_client().chat.completions.with_raw_response.create(
            model=settings.groq_llm_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": _INSTRUCTIONS.format(date=date, alertes=alertes)
                    + '\nRéponds en JSON avec exactement ces clés: {"objet": "...", "corps": "..."}',
                },
                {"role": "user", "content": rows_json},
            ],
        ), settings.groq_llm_model, "report")
        raw = resp.choices[0].message.content
        if not raw:
            raise ValueError("empty completion")
        return DailyReportContent.model_validate_json(raw)
    except DailyReportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DailyReportError(f"groq: {exc}") from exc


# Pipeline plumbing: true of the message, not of the work. Sent to the model it
# only costs tokens and invites a report that mentions which STT engine heard a
# voice note. Everything else in a row is kept, empty cells excepted — a Sheet
# row is ~60 columns and mostly blank, and the blanks are what makes the prompt
# large enough to push the real fields out of the model's attention.
_PLUMBING = frozenset({
    "_row", "lien_audio", "correlation_id", "confidence", "STT_model", "canal", "role",
})


# Only when there is something to say. A section reading "aucune alerte" every
# single evening is the fastest way to teach a director to skip that heading,
# and the day it is not empty it will be skipped too.
_ALERTS_SECTION = """
## Alertes matériel
Une puce par ligne du bloc ALERTES ci-dessous, reformulée en une phrase claire.
Reprends le chiffre, l'unité **et la provenance** entre parenthèses — un chiffre
sans sa source ne peut pas être contesté par celui qui le lit. Ne calcule aucune
quantité toi-même et n'ajoute aucune alerte qui ne figure pas dans le bloc.
Tu peux en revanche ajouter une puce **sans chiffre** pour un manque signalé
dans "besoins" ou "observations", en citant le texte du technicien.
"""


def _payload(rows: List[dict], alerts: Optional[List[dict]] = None) -> str:
    """The rows, trimmed, preceded by the totals already computed from them.

    The model used to be handed raw rows and asked to add them up in prose,
    which put the arithmetic in the one component that cannot be trusted with
    it: the mail body said one figure and the .docx table attached to the same
    mail said another. The totals now come from `journal.quantity_columns()` —
    the same catalogue the document's table is built from — so the two agree by
    construction rather than by luck.
    """
    from app import journal  # lazy: keeps this module importable without Sheets

    totals = {
        (f"{label} ({unit})" if unit else label):
            int(total) if float(total).is_integer() else total
        for _column, label, unit, total in journal.rapports_totals(rows)
    }
    trimmed = [
        {k: v for k, v in row.items() if k not in _PLUMBING and str(v or "").strip()}
        for row in rows
    ]
    # The findings arrive as sentences rather than as objects: they are already
    # decided, and the model's only job with them is French. Handed the raw
    # numbers it would start doing the arithmetic again.
    blocks = [
        "TOTAUX de la période (déjà calculés) :",
        json.dumps(totals or {"—": "aucune quantité chiffrée"}, ensure_ascii=False),
    ]
    if alerts:
        from app import stock

        blocks += ["", "ALERTES (déjà calculées, ne pas recalculer) :"]
        blocks += [f"- {stock.line(a)}" for a in alerts]
    blocks += ["", "Rapports (JSON) :", json.dumps(trimmed, ensure_ascii=False)]
    return "\n".join(blocks)


def generate_daily_report(
    date: str, rows: List[dict], alerts: Optional[List[dict]] = None
) -> DailyReportContent:
    """Primary engine with explicit fallback — never silent (both failures raise).

    `alerts` are `stock.assess`'s findings, computed by the caller rather than
    here: this module stays free of Sheets and Postgres, and the same list feeds
    the .docx table so the two cannot disagree.
    """
    rows_json = _payload(rows, alerts)
    section = _ALERTS_SECTION if alerts else ""
    try:
        return _generate_gemini(date, rows_json, section)
    except DailyReportError as primary_err:
        try:
            return _generate_groq(date, rows_json, section)
        except DailyReportError as fallback_err:
            raise DailyReportError(
                f"daily report failed on both engines — gemini: {primary_err} | groq: {fallback_err}"
            ) from fallback_err
