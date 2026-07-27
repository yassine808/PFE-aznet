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
    ("goulottes_m", "Goulottes (m)"),
    ("cables_m", "Câbles (m)"),
    ("bureaux_termines", "Bureaux terminés"),
    ("panneaux_raccordes", "Panneaux raccordés"),
)


def summarise(rows: List[Dict[str, Any]]) -> str:
    """Turn Sheet rows into the factual block the prompt renders.

    Computed here, in Python, rather than asking the model to add up the rows:
    a model that does arithmetic on the way to drawing will eventually draw a
    total nobody measured.
    """
    totals = {key: 0.0 for key, _ in _TOTALS}
    chantiers, techniciens = [], []
    for row in rows:
        for key, _ in _TOTALS:
            raw = row.get(key)
            try:
                totals[key] += float(str(raw).replace(",", ".")) if raw not in (None, "") else 0.0
            except (TypeError, ValueError):
                continue  # a non-numeric cell is a data problem, not a drawing problem
        for value, bucket in ((row.get("chantier"), chantiers), (row.get("technicien"), techniciens)):
            text = (value or "").strip()
            if text and text not in bucket:
                bucket.append(text)

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
        if provider.strip() != "gemini" or not model:
            failures.append(f"{entry}: only 'gemini:<model>' is supported")
            continue
        try:
            data, mime = _call_gemini(model.strip(), prompt)
            return data, mime, f"gemini/{model.strip()}"
        except ImageGenerationError as exc:
            failures.append(str(exc))
    raise ImageGenerationError("image generation failed on every model — " + " | ".join(failures))
