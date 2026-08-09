"""Image generation — the fourth model.

Produces an illustrated summary card for a day or a week, from rows that have
already been extracted. It is the only model in this service that *invents*
anything, so it is deliberately kept away from the report path: nothing it
returns is ever written to the Sheet, and the prompt forbids photorealism so a
generated picture can never be mistaken for a technician's own photo.

Free-tier note: Google's image models are metered far more tightly than the
text ones. This runs only on an explicit user action from the dashboard, never
on a cron and never per report.
"""
import base64
from typing import Any, Dict, List, Optional, Tuple

from app import prompt_loader
from app.config import settings


class ImageGenerationError(RuntimeError):
    pass


_PROMPT = prompt_loader.load(prompt_loader.IMAGE_GENERATION)

# Only fields that carry a number worth putting on a card. `resume` and free
# text are excluded on purpose: rendering prose into an image makes it
# unsearchable and uneditable, and it is already in the report.
_TOTALS = (
    ("cables_installes_m", "Câbles (m)"),
    ("goulotte_m", "Goulottes (m)"),
    ("prises_connectees", "Prises"),
    ("fibre_m", "Fibre (m)"),
)


def _accumulate_totals(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Sum each numeric field across rows; a non-numeric cell is skipped, not fatal."""
    totals = dict.fromkeys((key for key, _ in _TOTALS), 0.0)
    for row in rows:
        for key, _ in _TOTALS:
            raw = row.get(key)
            try:
                totals[key] += float(str(raw).replace(",", ".")) if raw not in (None, "") else 0.0
            except (TypeError, ValueError):
                continue  # a non-numeric cell is a data problem, not a drawing problem
    return totals


def _unique_names(rows: List[Dict[str, Any]], field: str) -> List[str]:
    """Distinct, order-preserving, non-empty values of `field` across rows."""
    return list(dict.fromkeys((row.get(field) or "").strip() for row in rows if (row.get(field) or "").strip()))


def summarise(rows: List[Dict[str, Any]]) -> str:
    """Turn Sheet rows into the factual block the prompt renders.

    Computed here, in Python, rather than asking the model to add up the rows:
    a model that does arithmetic on the way to drawing will eventually draw a
    total nobody measured.
    """
    totals = _accumulate_totals(rows)
    chantiers = _unique_names(rows, "chantier")
    techniciens = _unique_names(rows, "technicien")

    lines = [f"Rapports: {len(rows)}", f"Techniciens: {len(techniciens)}", f"Chantiers: {len(chantiers)}"]
    for key, label in _TOTALS:
        value = totals[key]
        if value:
            lines.append(f"{label}: {int(value) if value.is_integer() else value}")
    if chantiers:
        lines.append("Noms de chantiers: " + ", ".join(chantiers[:6]))
    return "\n".join(lines)


def _call_gemini(model: str, prompt: str) -> Tuple[bytes, str]:
    if not settings.gemini_api_key:
        raise ImageGenerationError("GEMINI_API_KEY not configured")
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
    except Exception as exc:  # noqa: BLE001
        raise ImageGenerationError(f"gemini/{model}: {exc}") from exc

    for candidate in resp.candidates or []:
        for part in getattr(candidate.content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                data = inline.data
                # The SDK returns raw bytes on some versions and base64 on others.
                if isinstance(data, str):
                    data = base64.b64decode(data)
                return data, getattr(inline, "mime_type", "image/png")
    raise ImageGenerationError(f"gemini/{model}: response contained no image part")


# ── the local card ─────────────────────────────────────────────────────────
# Drawn here, with no model at all.
#
# Google's free tier reports `limit: 0` for every image model — not a rate that
# resets, but "this is not available without billing". A chain of image models
# that are all the same vendor therefore has no working entry, and a feature
# that exists only when a metered quota happens to be open is not a feature the
# pilot can rely on.
#
# So the last entry in the chain draws the card from the numbers the summary
# already computed. It invents nothing, costs nothing and cannot fail, and it
# is the card that ends up in the .docx when the model path is unavailable.
# Which renderer produced it is reported back to the caller — this is a
# fallback the operator can see, never a silent substitution.

_CARD_SIZE = (1200, 675)  # 16:9, the ratio the .docx export lays out for


def _font(size: int, bold: bool = False):
    """A scalable font, wherever this happens to be running.

    The API runs in a slim image with no system fonts and on a Windows host
    with a different set again, so each candidate is tried in turn. The last
    resort is `load_default(size)` — Pillow ≥ 10.1 bundles a scalable font
    for it. `load_default()` *without* a size is the trap: it returns a
    fixed bitmap face that silently ignores `size` and cannot draw `é`, so
    the card comes out in tiny mojibake instead of failing.

    Module level rather than nested in `_draw_card`, because the mail banner
    (`app.mailer.banner_png`) needs exactly this fallback chain and a second
    copy of it would drift the first time one of them gains a candidate.
    """
    from PIL import ImageFont

    candidates = (
        ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
        ("arialbd.ttf", "arial.ttf"),
        ("LiberationSans-Bold.ttf", "LiberationSans-Regular.ttf"),
    )
    for bold_name, regular_name in candidates:
        try:
            return ImageFont.truetype(bold_name if bold else regular_name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _draw_card(title: str, rows: List[Dict[str, Any]]) -> Tuple[bytes, str]:
    """A flat, typographic summary card. Pillow only, no network."""
    import io

    from PIL import Image, ImageDraw

    ink = (15, 23, 42)
    muted = (100, 116, 139)
    accent = (37, 99, 235)
    canvas = Image.new("RGB", _CARD_SIZE, (248, 250, 252))
    draw = ImageDraw.Draw(canvas)
    font = _font

    totals = _accumulate_totals(rows)
    chantiers = _unique_names(rows, "chantier")
    techniciens = _unique_names(rows, "technicien")

    draw.rectangle((0, 0, _CARD_SIZE[0], 12), fill=accent)
    draw.text((64, 72), title, font=font(46, bold=True), fill=ink)
    draw.text((64, 140), "aznet · rapport de chantier", font=font(24), fill=muted)

    cells = [
        (str(len(rows)), "Rapports"),
        (str(len(techniciens)), "Techniciens"),
        (str(len(chantiers)), "Chantiers"),
    ]
    for key, label in _TOTALS:
        value = totals[key]
        if value:
            cells.append((str(int(value) if value.is_integer() else value), label))

    for index, (value, label) in enumerate(cells[:8]):
        # 4 per row: the 3 fixed cells plus all 4 totals fit without silently
        # dropping the last one (6 cells dropped "Fibre (m)" on a full day).
        x = 64 + (index % 4) * 290
        y = 240 + (index // 4) * 180
        draw.text((x, y), value, font=font(64, bold=True), fill=accent)
        draw.text((x, y + 82), label, font=font(24), fill=muted)

    if chantiers:
        draw.text((64, 600), " · ".join(chantiers[:4]), font=font(22), fill=muted)

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def generate_card(rows: List[Dict[str, Any]], title: str, extra: Optional[str] = None) -> Tuple[bytes, str, str]:
    """Render a summary card. Returns (image bytes, mime type, winning model).

    Tries each model in `IMAGE_GENERATION_CHAIN` in order, same contract as the
    extraction chains: first success wins, total failure raises with every
    reason listed.
    """
    context = summarise(rows)
    prompt = f"{_PROMPT}\n\nTitre: {title}\n{context}"
    if extra:
        prompt += f"\n\nDemande de l'utilisateur: {extra}"

    failures = []
    for entry in settings.image_generation_chain.split(","):
        entry = entry.strip()
        if not entry:
            continue
        provider, _, model = entry.partition(":")
        if provider.strip() == "local":
            data, mime = _draw_card(title, rows)
            return data, mime, "local"
        if provider.strip() != "gemini" or not model:
            failures.append(f"{entry}: only 'gemini:<model>' or 'local' is supported")
            continue
        try:
            data, mime = _call_gemini(model.strip(), prompt)
            return data, mime, f"gemini/{model.strip()}"
        except ImageGenerationError as exc:
            failures.append(str(exc))
    raise ImageGenerationError("image generation failed on every model — " + " | ".join(failures))
