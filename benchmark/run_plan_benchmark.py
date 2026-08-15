"""Vision benchmark — annotated floor plans.

A different question from `run_model_benchmark.py --mode image`. That one asks
"can you read a written number off a page"; this one asks "can you see where
someone drew on a plan, and can you resist describing the parts they did not
draw on".

The criterion is fixed before the run, as it was for STT: **localization
accuracy**. A model is scored on

  rappel        — of the zones actually marked (dataset/plan_cases.json:attendu)
  hallucination — zones printed on the plan but NOT marked in this photo, that
                  the model claims anyway (…:interdit)

Counting marks is deliberately NOT graded. Counting discrete dots on a phone
photo of a plan is the thing vision models are worst at, and a wrong count in a
numeric column becomes a wrong contract total that nobody catches. Zones feed
`etages` / `ailes` / `locaux_techniques`, which is what the journal consumes.

The three photographs are the same plan in three annotation states, so the
printed layout is a constant and the marks are the only variable — a claim
about an unmarked zone is provably false rather than merely unverified. What
this cannot measure: a different building, different handwriting, a worse
photograph. One plan is one plan.

Usage (from benchmark/, with the api venv):
    ../api/.venv/Scripts/python.exe run_plan_benchmark.py
    ../api/.venv/Scripts/python.exe run_plan_benchmark.py --models gemini-3.6-flash
    ../api/.venv/Scripts/python.exe run_plan_benchmark.py --cases p01_cercle_bloc_est
"""
import argparse
import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))
sys.path.insert(0, str(BENCH_DIR.parent / "api"))

from app.config import settings  # noqa: E402

CASES = BENCH_DIR / "dataset" / "plan_cases.json"
IMAGE_DIR = BENCH_DIR / "dataset" / "images"
RESULTS_DIR = BENCH_DIR / "results"

# Google first because the image chain is Google-only today. Groq's Llama 4
# models ARE multimodal, unlike the rest of its free catalogue — the
# "no vision model on Groq" note in CLAUDE.md predates them, and whether they
# actually serve images on the free tier is itself a finding this run reports.
GEMINI_VISION = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]
GROQ_VISION = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]

# Free-form prose, not the report schema. Asking for `ExtractedReport` here
# would grade the wrong thing: a plan carries no metres, and forcing it through
# a quantity schema invites exactly the invented numbers this run exists to
# avoid. `zones` is the graded field; `description` is for the human reading
# the results table.
PROMPT = """Cette image est la photo d'un plan d'architecte affiché sur un mur.
Des techniciens de câblage réseau ont dessiné dessus, à la main, pour indiquer
où ils travaillent : traits de couleur, points, tracés, entourages.

Ta tâche : dire OÙ se trouvent ces annotations, en t'appuyant sur les
étiquettes déjà imprimées sur le plan (numéros de chambre, RECEPTION, BAR,
Restaurant, salle de réunion, RECEP, DOUCHE, MAGAZIN...).

Réponds en JSON strict :
{
  "zones": ["...", "..."],
  "annotations": "ce qui est dessiné (couleurs, formes), en une phrase",
  "description": "2-3 phrases : ce que les marques semblent indiquer"
}

Règles :
- `zones` ne contient QUE des endroits effectivement marqués. Une pièce
  imprimée sur le plan mais non annotée ne doit PAS y figurer.
- Nomme les zones avec les mots du plan ("chambres 1017-1035", "bloc RECEP",
  "BAR nord-est"), pas en coordonnées.
- Ne compte pas les marques et n'invente aucune quantité en mètres.
- Si aucune annotation manuscrite n'est visible, `zones` est une liste vide.
"""


def _fold(text: str) -> str:
    """Lowercase, accent-stripped, for substring matching.

    The key says "réception" and a model may write "reception"; that is the
    same zone, and a benchmark that scores the accent measures the tokenizer
    instead of the vision.
    """
    stripped = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def load_cases() -> List[dict]:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    for case in data["cases"]:
        if not (IMAGE_DIR / case["image"]).exists():
            raise FileNotFoundError(f"{case['id']}: missing {case['image']}")
        if not case.get("attendu"):
            raise ValueError(f"{case['id']}: no expected zones to grade")
    return data["cases"]


# --------------------------------------------------------------------------- #
# Engines. Each returns (parsed_dict, latency_s) or raises.
# --------------------------------------------------------------------------- #
def call_gemini(model: str, image: bytes, mime: str) -> Tuple[Dict[str, Any], float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    t0 = time.time()
    resp = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image, mime_type=mime), PROMPT],
        config={"response_mime_type": "application/json"},
    )
    latency = time.time() - t0
    # A blocked or empty response returns None here, not an exception. Left
    # unguarded it becomes a TypeError deep in json, which reads like a bug in
    # the harness rather than what it is: a refusal by the model, which is a
    # real result about the candidate.
    if not resp.text:
        raise RuntimeError(f"réponse vide (finish_reason={_finish_reason(resp)})")
    return json.loads(resp.text), latency


def _finish_reason(resp) -> str:
    try:
        return str(resp.candidates[0].finish_reason)
    except Exception:  # noqa: BLE001
        return "inconnu"


def call_groq(model: str, image: bytes, mime: str) -> Tuple[Dict[str, Any], float]:
    import base64

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    latency = time.time() - t0
    content = resp.choices[0].message.content
    if not content:
        raise RuntimeError("réponse vide")
    return json.loads(content), latency


def call_with_retry(engine, model: str, image: bytes, mime: str):
    """Retry on rate limiting only — a 429 scores the quota, not the model.

    Same rule as run_model_benchmark.call_with_retry; every other exception
    propagates, because a 404 or a refusal is a real result about the candidate.
    """
    for attempt in range(4):
        try:
            return engine(model, image, mime)
        except Exception as exc:  # noqa: BLE001
            text = str(exc).lower()
            transient = "429" in text or "resource_exhausted" in text or "rate limit" in text
            if not transient or attempt == 3:
                raise
            wait = 20 * (attempt + 1)
            print(f"    rate limited, waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def engine_for(model: str):
    return call_groq if model.startswith("meta-llama/") else call_gemini


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score(case: dict, answer: Dict[str, Any]) -> Dict[str, Any]:
    """Recall over marked zones, plus hallucinated zones.

    Matching is substring-on-folded-text in BOTH directions: the model's
    "chambres 1017 à 1035" must hit the key's "1017", and its bare "recep" must
    hit "bloc est (RECEP / douches)". A zone counts once however many times it
    is named.

    `annotations` and `description` are searched too, not just `zones`: a model
    that names the right place in prose but leaves `zones` empty has still seen
    the plan correctly, and grading only the list would score instruction
    following rather than vision. Hallucinations are searched in `zones` ONLY —
    prose mentioning "le restaurant n'est pas marqué" is correct, not a claim.
    """
    zones = answer.get("zones") or []
    if isinstance(zones, str):
        zones = [zones]
    zone_text = _fold(" | ".join(str(z) for z in zones))
    all_text = _fold(" | ".join(
        [zone_text, str(answer.get("annotations", "")), str(answer.get("description", ""))]
    ))

    hits, misses = [], []
    for expected in case["attendu"]:
        needles = [expected["zone"]] + expected.get("synonymes", [])
        if any(_fold(n) in all_text for n in needles):
            hits.append(expected["zone"])
        else:
            misses.append(expected["zone"])

    hallucinated = [bad for bad in case.get("interdit", []) if _fold(bad) in zone_text]
    return {
        "rappel": len(hits) / len(case["attendu"]),
        "trouve": hits,
        "manque": misses,
        "hallucine": hallucinated,
        "n_zones": len(zones),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="comma-separated; default = every candidate")
    ap.add_argument("--cases", help="comma-separated case ids")
    ap.add_argument("--out", default=None, help="results json path")
    args = ap.parse_args()

    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    models = args.models.split(",") if args.models else GEMINI_VISION + GROQ_VISION

    images = {
        c["id"]: (IMAGE_DIR / c["image"]).read_bytes() for c in cases
    }
    mimes = {
        c["id"]: ("image/png" if c["image"].lower().endswith(".png") else "image/jpeg")
        for c in cases
    }

    results: List[Dict[str, Any]] = []
    for model in models:
        print(f"\n=== {model}", flush=True)
        engine = engine_for(model)
        for case in cases:
            try:
                answer, latency = call_with_retry(engine, model, images[case["id"]], mimes[case["id"]])
            except Exception as exc:  # noqa: BLE001 - an unreachable model is a finding
                print(f"  {case['id']:28} INDISPONIBLE — {str(exc)[:120]}", flush=True)
                results.append({
                    "model": model, "case": case["id"], "erreur": str(exc)[:400],
                })
                continue
            marks = score(case, answer)
            flag = " HALLU" if marks["hallucine"] else ""
            print(
                f"  {case['id']:28} rappel {marks['rappel']:.0%}  "
                f"{latency:5.1f}s  zones={marks['n_zones']}{flag}",
                flush=True,
            )
            if marks["manque"]:
                print(f"      manque   : {marks['manque']}", flush=True)
            if marks["hallucine"]:
                print(f"      hallucine: {marks['hallucine']}", flush=True)
            results.append({
                "model": model, "case": case["id"], "latence_s": round(latency, 2),
                "reponse": answer, **marks,
            })

    # Per-model summary. A model that hallucinates is reported separately from
    # one that simply misses: a miss costs a column, a hallucination writes a
    # wrong floor into the journal, and they are not the same failure.
    print("\n" + "=" * 72)
    print(f"{'model':46} {'rappel':>7} {'hallu':>6} {'lat':>6}")
    print("-" * 72)
    for model in models:
        rows = [r for r in results if r["model"] == model and "erreur" not in r]
        failed = [r for r in results if r["model"] == model and "erreur" in r]
        if not rows:
            print(f"{model:46} {'INDISPONIBLE':>20}")
            continue
        rappel = sum(r["rappel"] for r in rows) / len(rows)
        hallu = sum(len(r["hallucine"]) for r in rows)
        lat = sum(r["latence_s"] for r in rows) / len(rows)
        suffix = f"  ({len(failed)} échec)" if failed else ""
        print(f"{model:46} {rappel:6.0%} {hallu:6d} {lat:5.1f}s{suffix}")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else RESULTS_DIR / f"plan-benchmark-{stamp}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
