"""Render the report e-mail to a file so it can be looked at.

The one thing nobody can review in a diff is whether a message *looks* right,
and the only other way to find out is to send one — which needs SMTP
credentials and a mailbox. This writes the same HTML `jobs._report_html`
produces, with the banner inlined as a data URI so a browser shows what the
recipient's client will show (the real message attaches it by Content-ID; a
`data:` URI is what Gmail strips, hence the difference).

    cd api
    .venv/Scripts/python.exe scripts/preview_mail.py
    # → api/preview-mail.html, ignored by git

No credentials, no network, no side effects.
"""
import base64
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import mailer  # noqa: E402

SAMPLE = """## Synthèse
La journée a enregistré 8 interventions menées par 3 techniciens, couvrant 240 mètres \
de goulottes et 610 mètres de câbles.

## Détail par chantier
- Sidi Maarouf — Yassine : pose de 120 m de goulottes, raccordement de 4 panneaux.
- Aïn Sebaâ — Karim : 90 m de câble tiré, 2 bureaux terminés.
- Anfa — Rachid : reprise de brassage, aucun métrage déclaré.

## Problèmes et besoins
- Une transcription vocale incomplète a été signalée pour vérification.
"""


def main() -> None:
    caption = "Rapport du jour"
    html = mailer.render_document(
        title="Rapport du jour — 5 août 2026",
        lead=SAMPLE,
        rows=[("Rapports", "8"), ("Techniciens", "3"), ("À vérifier", "1")],
        cta=("Ouvrir le rapport", "http://localhost:8080/#/daily?date=2026-08-05"),
        footer="Envoi automatique du tableau de bord aznet.",
        caption=caption,
        rich=True,
    )
    png = mailer.banner_png(caption)
    html = html.replace(
        f"cid:{mailer._banner_cid(caption)}",
        "data:image/png;base64," + base64.b64encode(png).decode(),
    )
    out = pathlib.Path(__file__).resolve().parents[1] / "preview-mail.html"
    out.write_text(html, encoding="utf-8")
    print(f"{out}  ({len(png)} B banner)")


if __name__ == "__main__":
    main()
