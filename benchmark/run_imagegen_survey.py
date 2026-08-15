"""Image generation — reachability survey.

Quality cannot be judged among endpoints that never answer, and `config.py`
already records the finding that Google's free tier returns `limit: 0` for
every image model — not a rate that resets, but "not on the free tier at all".
That claim is from one vendor on one date, so this re-tests it and widens the
net to the other free image endpoints a zero-budget project could reach.

What this reports per candidate:

  OK           bytes came back, with size and latency — a real candidate
  QUOTA        reachable but metered to zero / billing required — the finding
  AUTH         no key configured here — not a verdict on the endpoint
  ERROR        anything else, message kept

Only the OK row deserves a quality run afterwards. An endpoint that needs a
card is not a candidate for this project, however good its output is.

Usage (from benchmark/, with the api venv):
    ../api/.venv/Scripts/python.exe run_imagegen_survey.py
    ../api/.venv/Scripts/python.exe run_imagegen_survey.py --save
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))
sys.path.insert(0, str(BENCH_DIR.parent / "api"))

from app.config import settings  # noqa: E402

RESULTS_DIR = BENCH_DIR / "results"

# The same card the dashboard asks for, so a reachable model is tested on the
# real job rather than on a landscape it will never be asked to draw. Text
# rendering is deliberately in the prompt: a summary card that cannot spell
# "Câbles" in French is not usable, and that is where these models fail first.
PROMPT = (
    "Illustration vectorielle plate, style rapport d'entreprise, sans photoréalisme. "
    "Carte de synthèse d'un chantier de câblage réseau. "
    "Texte français lisible : « Câbles 2 274 m », « Goulottes 810 m », « Prises 46 ». "
    "Palette sobre bleu et gris, fond clair, format paysage 16:9."
)

_QUOTA_MARKERS = (
    "limit: 0", "quota", "billing", "resource_exhausted", "429",
    "free tier", "not available", "insufficient",
)
_AUTH_MARKERS = ("api key", "unauthorized", "401", "403", "authentication", "no key")


def classify(exc: Exception) -> str:
    text = str(exc).lower()
    if any(m in text for m in _AUTH_MARKERS):
        return "AUTH"
    if any(m in text for m in _QUOTA_MARKERS):
        return "QUOTA"
    return "ERROR"


# --------------------------------------------------------------------------- #
# Candidates. Each returns raw image bytes or raises.
# --------------------------------------------------------------------------- #
def probe_gemini(model: str) -> bytes:
    if not settings.gemini_api_key:
        raise RuntimeError("no key: GEMINI_API_KEY")
    from app import imagegen

    data, _mime = imagegen._call_gemini(model, PROMPT)
    return data


def probe_pollinations(model: str) -> bytes:
    """Keyless public endpoint — the only one needing no account at all.

    Included precisely because "works with no key" is the strongest possible
    answer to the zero-budget constraint; if it returns usable pixels it beats
    a better model that needs a card.
    """
    import urllib.parse
    import urllib.request

    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(PROMPT)
        + f"?width=1200&height=675&nologo=true&model={model}"
    )
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    if not data.startswith((b"\x89PNG", b"\xff\xd8")):
        raise RuntimeError(f"not an image: {data[:80]!r}")
    return data


def probe_hf(model: str) -> bytes:
    token = os.environ.get("HF_TOKEN") or getattr(settings, "hf_token", None)
    if not token:
        raise RuntimeError("no key: HF_TOKEN")
    import urllib.request

    req = urllib.request.Request(
        f"https://api-inference.huggingface.co/models/{model}",
        data=json.dumps({"inputs": PROMPT}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
    if not data.startswith((b"\x89PNG", b"\xff\xd8")):
        raise RuntimeError(f"not an image: {data[:160]!r}")
    return data


def probe_cloudflare(model: str) -> bytes:
    account = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not (account and token):
        raise RuntimeError("no key: CF_ACCOUNT_ID / CF_API_TOKEN")
    import urllib.request

    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}",
        data=json.dumps({"prompt": PROMPT}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
    if data.startswith(b"{"):
        raise RuntimeError(json.loads(data).get("errors", data[:160]))
    return data


CANDIDATES: List[Tuple[str, str, Callable[[str], bytes]]] = [
    ("gemini", "gemini-3.1-flash-image", probe_gemini),
    ("gemini", "nano-banana-pro-preview", probe_gemini),
    ("gemini", "gemini-3-pro-image", probe_gemini),
    ("pollinations", "flux", probe_pollinations),
    ("pollinations", "turbo", probe_pollinations),
    ("hf", "black-forest-labs/FLUX.1-schnell", probe_hf),
    ("hf", "stabilityai/stable-diffusion-xl-base-1.0", probe_hf),
    ("cloudflare", "@cf/black-forest-labs/flux-1-schnell", probe_cloudflare),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="write returned images for eyeballing")
    args = ap.parse_args()

    out_dir = RESULTS_DIR / "imagegen-survey"
    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict] = []
    for vendor, model, probe in CANDIDATES:
        label = f"{vendor}/{model}"
        t0 = time.time()
        try:
            data = probe(model)
        except Exception as exc:  # noqa: BLE001 - the classification IS the result
            verdict = classify(exc)
            print(f"{label:52} {verdict:6} {str(exc)[:70]}", flush=True)
            rows.append({"vendor": vendor, "model": model, "verdict": verdict,
                         "erreur": str(exc)[:400]})
            continue
        latency = time.time() - t0
        print(f"{label:52} {'OK':6} {len(data)/1024:7.0f} KB  {latency:5.1f}s", flush=True)
        rows.append({"vendor": vendor, "model": model, "verdict": "OK",
                     "octets": len(data), "latence_s": round(latency, 2)})
        if args.save:
            ext = "png" if data.startswith(b"\x89PNG") else "jpg"
            (out_dir / f"{vendor}-{model.replace('/', '_')}.{ext}").write_bytes(data)

    usable = [r for r in rows if r["verdict"] == "OK"]
    print("\n" + "=" * 72)
    print(f"joignables: {len(usable)}/{len(rows)}")
    for r in usable:
        print(f"  {r['vendor']}/{r['model']}")
    if not usable:
        print("  aucun — le rendu Pillow déterministe reste le seul chemin")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"imagegen-survey-{stamp}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
