"""Render every outgoing message to one file so the layout can be looked at.

The one thing nobody can review in a diff is whether a message *looks* right,
and the only other way to find out is to send one — which needs SMTP
credentials and a mailbox. This writes the exact HTML the scheduler produces,
for all three shapes it sends, stacked in one page:

    cd api
    .venv/Scripts/python.exe scripts/preview_mail.py
    # → api/preview-mail.html, ignored by git

Nothing is faked in the renderer: the samples go through `jobs._report_html`
and `jobs._reminder_html` themselves, so a change to either shows up here. No
credentials, no network, no side effects.
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import jobs, mailer  # noqa: E402
from app.daily_report import DailyReportContent  # noqa: E402

DAILY = """## Synthèse
La journée a enregistré 8 interventions menées par 3 techniciens sur 3 chantiers, \
pour 240 mètres de goulottes posées, 610 mètres de câbles installés et 12 prises \
testées.

## Détail par chantier
- Sidi Maarouf — Yassine : pose de 120 m de goulottes, raccordement de 4 panneaux, \
RDC et 1er étage, aile Nord.
- Aïn Sebaâ — Karim : 90 m de câble tiré, 2 bureaux terminés, local technique SR2.
- Anfa — Rachid : reprise de brassage, aucun métrage déclaré.

## Problèmes et besoins
- Une transcription vocale incomplète a été signalée pour vérification.
- Bureaux du 2e étage fermés : équipe arrêtée 1 h 30 sur instruction du client.
- Stock goulottes à Sidi Maarouf : écart de 40 m entre le relevé et le calcul.
"""

WEEKLY = """## Synthèse
La semaine totalise 37 interventions, 5 techniciens mobilisés et 4 chantiers \
couverts, pour 1 480 mètres de goulottes et 3 210 mètres de câbles.

## Détail par chantier
- Sidi Maarouf — 18 rapports : 720 m de goulottes, 24 bureaux terminés.
- Aïn Sebaâ — 11 rapports : 430 m de goulottes, 9 panneaux raccordés.
- Anfa — 8 rapports : fibre, 260 m tirés et 48 brins raccordés.

## Problèmes et besoins
- Deux journées perdues à Anfa faute d'accès aux locaux techniques.
"""


def main() -> None:
    parts = [
        (
            "Rapport journalier (jobs._report_html)",
            jobs._report_html(
                "2026-08-05",
                DailyReportContent(
                    objet="Rapport journalier — 5 août 2026 — 8 interventions",
                    corps=DAILY,
                ),
                8,
            ),
        ),
        (
            "Rapport hebdomadaire (jobs._report_html)",
            jobs._report_html(
                "2026-08-03 → 2026-08-09",
                DailyReportContent(
                    objet="Rapport hebdomadaire — semaine du 3 août 2026",
                    corps=WEEKLY,
                ),
                37,
            ),
        ),
        (
            # The reminder is the shape that mixes a date (ledger) with free
            # prose (its own band) — the case `_is_figure` exists for.
            "Rappel de tâche (jobs._reminder_html)",
            jobs._reminder_html(
                {
                    "title": "Livraison du bordereau — Sidi Maarouf",
                    "due_at": datetime.datetime(2026, 8, 7, 14, 0),
                    "remind_before_value": 3,
                    "remind_before_unit": "day",
                    "notes": "Vérifier les quantités posées contre le contrat avant "
                    "envoi au client, et joindre le relevé de stock du local SR2.",
                }
            ),
        ),
        (
            # Straight from the endpoint's own generator, so the figures are
            # different on every render — which is the point of it.
            "Test de notification (POST /notify/test)",
            mailer.sample_report("directeur@aznet.ma")[1],
        ),
    ]
    page = "".join(
        f'<p style="max-width:{mailer.WIDTH}px;margin:32px auto 0;font:600 12px/1.4 '
        f'ui-monospace,monospace;color:#64748b;letter-spacing:1px;'
        f'text-transform:uppercase">{label}</p>{html}'
        for label, html in parts
    )
    out = pathlib.Path(__file__).resolve().parents[1] / "preview-mail.html"
    out.write_text(
        f'<!doctype html><meta charset="utf-8"><title>aznet — aperçu des e-mails</title>'
        f'<body style="margin:0;background:#f1f5f9">{page}<div style="height:48px"></div></body>',
        encoding="utf-8",
    )
    print(f"{out}  ({len(parts)} messages)")


if __name__ == "__main__":
    main()
