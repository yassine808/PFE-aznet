"""Model benchmark for the text and image paths (audio has its own harness).

Scores every candidate model on the same hand-written cases in
`dataset/text_cases.json` and reports field accuracy, hallucination rate and
latency, so the choice of primary/fallback in `app/config.py` is evidence and
not taste.

Usage (from benchmark/, with the api venv):
    ../api/.venv/Scripts/python.exe run_model_benchmark.py --mode text
    ../api/.venv/Scripts/python.exe run_model_benchmark.py --mode image
    ../api/.venv/Scripts/python.exe run_model_benchmark.py --mode text --models gemini-3.6-flash,openai/gpt-oss-120b
    ../api/.venv/Scripts/python.exe run_model_benchmark.py --mode text --models openai/gpt-oss-120b --cases t04_hallucination_trap,t08_no_quantities_at_all
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
import pathlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))
sys.path.insert(0, str(BENCH_DIR.parent / "api"))

from metrics import extraction_accuracy  # noqa: E402

from app.config import settings  # noqa: E402
from app.extraction import _INSTRUCTIONS  # noqa: E402
from app.schemas import ExtractedReport  # noqa: E402

CASES = BENCH_DIR / "dataset" / "text_cases.json"
IMAGE_DIR = BENCH_DIR / "dataset" / "images"
RESULTS_DIR = BENCH_DIR / "results"


def results_path(name: str, ext: str = "json") -> pathlib.Path:
    """`results/<YYYY-MM-DD>/<name>-<HHMMSS>.<ext>`, parents created.

    Runs are grouped by the day they were taken because a benchmark result is
    only meaningful next to its date: free-tier catalogues change under you
    (models 404 that answered last week), and a ranking quoted without the day
    it was measured is not evidence. The time still lives in the filename, so
    two runs on the same day never collide.
    """
    from datetime import datetime

    now = datetime.now()
    day = RESULTS_DIR / now.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    return day / f"{name}-{now.strftime('%H%M%S')}.{ext}"

# Candidates: every model the two keys actually serve that could plausibly do
# structured extraction, enumerated from the live catalogues on 2026-08-15
# (`client.models.list()`), not hand-picked. Excluded by kind rather than by
# taste: TTS, image, video, robotics, music, computer-use, deep-research and
# the guard classifiers cannot return a filled schema, and Whisper is the STT
# harness's business.
#
# Two entries are deliberately re-tried after being dropped on 2026-07-27:
# gemini-2.5-flash 404'd ("no longer available to new users") and
# gemini-3.5-flash answered 503 on 10/10 calls. Both are listed by the API
# again today, and a free catalogue that changed under us once will change
# again — so their status is re-measured rather than remembered. That is the
# whole reason results are filed by date.
GEMINI_TEXT = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]
# Groq's whole free text catalogue. `allam-2-7b` earns its place for a reason
# the others do not have: it is Arabic-first, and the source material is
# Darija — the one candidate with a claim to beat the rest on this corpus
# specifically rather than on general benchmarks.
GROQ_TEXT = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-safeguard-20b",
    "qwen/qwen3.6-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "groq/compound",
    "groq/compound-mini",
    "allam-2-7b",
]
GEMINI_VISION = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]

IMAGE_INSTRUCTIONS = (
    "Cette image est une photo prise par un technicien de câblage : page de carnet, "
    "tableau blanc, bon de livraison ou vue du chantier. Lis tout le texte visible "
    "(français, darija en lettres latines ou arabe) et extrais le rapport.\n"
) + _INSTRUCTIONS


def load_cases() -> List[dict]:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = data["cases"]
    for c in cases:
        if not c.get("expected"):
            raise ValueError(f"{c['id']}: no expected fields to grade")
    return cases


# --------------------------------------------------------------------------- #
# Engines. Each returns (parsed_dict, latency_s) or raises.
# --------------------------------------------------------------------------- #
def call_gemini(model: str, text: str, image: Optional[bytes] = None) -> Tuple[Dict[str, Any], float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    if image is None:
        contents: Any = _INSTRUCTIONS + text
    else:
        contents = [
            types.Part.from_bytes(data=image, mime_type="image/png"),
            IMAGE_INSTRUCTIONS,
        ]
    t0 = time.time()
    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config={"response_mime_type": "application/json", "response_schema": ExtractedReport},
    )
    latency = time.time() - t0
    parsed = resp.parsed
    if not isinstance(parsed, ExtractedReport):
        raise RuntimeError(f"unparseable response: {resp.text!r:.200}")
    return parsed.model_dump(), latency


def call_groq(model: str, text: str, image: Optional[bytes] = None) -> Tuple[Dict[str, Any], float]:
    if image is not None:
        raise RuntimeError("no vision model in the Groq free catalogue")
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    schema_hint = json.dumps(
        {k: v.get("type", "string") for k, v in ExtractedReport.model_json_schema()["properties"].items()},
        ensure_ascii=False,
    )
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _INSTRUCTIONS + f"\nRéponds en JSON avec exactement ces clés: {schema_hint}"},
            {"role": "user", "content": text},
        ],
    )
    latency = time.time() - t0
    return ExtractedReport.model_validate_json(resp.choices[0].message.content).model_dump(), latency


def call_with_retry(engine, model: str, text: str, image: Optional[bytes]) -> Tuple[Dict[str, Any], float]:
    """Retry on rate limiting only.

    Free tiers meter per minute, so a 429 mid-run says "wait", not "this model
    is bad" — counting it as a failure would score the quota instead of the
    model. Every other exception propagates: a 404 or a schema violation is a
    real result about the candidate.
    """
    for attempt in range(4):
        try:
            return engine(model, text, image)
        except Exception as exc:  # noqa: BLE001
            transient = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "rate limit" in str(exc).lower()
            if not transient or attempt == 3:
                raise
            wait = 20 * (attempt + 1)
            print(f"    rate limited, waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def engine_for(model: str):
    """Vendor by membership, not by name.

    This used to guess from the string ("/" in it, or a llama/qwen prefix).
    That held only while the lists were four names each: `allam-2-7b` and
    `gemma-4-31b-it` both break it, and the failure is quiet — the call goes to
    the wrong vendor and comes back as a 404 that reads like a dead model
    rather than a routing bug in the harness.
    """
    if model in GROQ_TEXT:
        return call_groq
    if model in GEMINI_TEXT or model in GEMINI_VISION:
        return call_gemini
    raise SystemExit(f"unknown model {model!r}: add it to GEMINI_TEXT or GROQ_TEXT")


# --------------------------------------------------------------------------- #
# Image fixtures: the cases rendered as a photographed notebook page.
# --------------------------------------------------------------------------- #
def render_images(cases: List[dict]) -> Dict[str, bytes]:
    """Render each case as a handwritten-looking note on ruled paper.

    ponytail: rendered text, not real photographs — there is no photo dataset
    yet, and a rendered page still exercises the part that matters here (read
    the page, map the words onto the schema). It does NOT measure robustness to
    blur, glare or skew; record real photos before trusting the image path in
    production. Deterministic and gitignored, so it costs nothing to regenerate.
    """
    from PIL import Image, ImageDraw, ImageFont

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out: Dict[str, bytes] = {}
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, 26)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("no TrueType font found; Arabic and accents need one")

    for case in cases:
        w, h = 1000, 700
        img = Image.new("RGB", (w, h), (250, 248, 240))
        d = ImageDraw.Draw(img)
        for y in range(80, h, 44):  # ruled lines
            d.line([(50, y), (w - 50, y)], fill=(210, 215, 228), width=1)
        d.text((50, 30), "Rapport journalier", font=font, fill=(60, 60, 70))

        # Wrap by width, not character count: Arabic glyphs are much wider.
        words, line, y = case["text"].split(), "", 92
        for word in words:
            trial = f"{line} {word}".strip()
            if d.textlength(trial, font=font) > w - 120:
                d.text((60, y), line, font=font, fill=(25, 30, 45))
                y, line = y + 44, word
            else:
                line = trial
        if line:
            d.text((60, y), line, font=font, fill=(25, 30, 45))

        path = IMAGE_DIR / f"{case['id']}.png"
        img.save(path)
        out[case["id"]] = path.read_bytes()
    return out


# --------------------------------------------------------------------------- #
def hallucination_detail(expected: Dict[str, Any], actual: Dict[str, Any]) -> Tuple[int, int]:
    """(invented, expected_nulls) — fields the reference says are absent that the model filled anyway."""
    nulls = [k for k, v in expected.items() if v is None]
    invented = sum(1 for k in nulls if actual.get(k) not in (None, "", []))
    return invented, len(nulls)


def _run_case(engine, model: str, case: dict, image: object, sleep_s: float, csv_file, writer) -> dict:
    """Score one model against one case, print progress, write the CSV row. Any
    exception from the engine is recorded as a failed row, not raised: a dead
    model is a result to report, not a reason to abort the whole run.
    """
    expected = case["expected"]
    try:
        actual, latency = call_with_retry(engine, model, case["text"], image)
        acc, detail = extraction_accuracy(expected, actual)
        invented, nulls = hallucination_detail(expected, actual)
        wrong = [k for k, ok in detail.items() if not ok]
        row = {
            "model": model, "case": case["id"], "accuracy": round(acc, 3),
            "latency_s": round(latency, 2), "invented": invented, "expected_nulls": nulls,
            "wrong_fields": "|".join(wrong), "error": "",
        }
        # ASCII only: the Windows console is cp1252 and a UnicodeEncodeError
        # here would kill the run on exactly the cases that found a mistake.
        print(f"  {case['id']:<24} acc={acc:.0%} {latency:5.2f}s "
              f"{'invented=' + str(invented) if invented else ''} {'WRONG: ' + ','.join(wrong) if wrong else ''}",
              flush=True)
    except Exception as exc:  # a dead model is a result, not a crash  # noqa: BLE001
        row = {
            "model": model, "case": case["id"], "accuracy": "", "latency_s": "",
            "invented": "", "expected_nulls": "", "wrong_fields": "",
            "error": str(exc)[:300],
        }
        print(f"  {case['id']:<24} ERROR {str(exc)[:160]}", flush=True)
    writer.writerow(row)
    csv_file.flush()
    time.sleep(sleep_s)
    return row


def _print_leaderboard(models: List[str], rows: List[dict]) -> None:
    """Coverage, then hallucinations, then accuracy, then latency.

    Accuracy alone made llama-3.3-70b-versatile the 2026-08-15 "winner" on
    100% — of the SEVEN cases out of twenty it answered at all. A model that
    refuses two thirds of the corpus and is perfect on the rest is not the one
    to put in front of a technician: in a fallback chain it spends its attempt
    and falls through. So an errored run counts as coverage lost, and a
    candidate that cannot answer most of the corpus cannot win however good its
    answers are. Hallucinations rank above accuracy for the same reason they do
    in the vision benchmark — a fast model that invents a quantity is worse
    than a slow one that says null.
    """
    print(f"\n{'model':<32} {'acc':>6} {'invented':>9} {'p50 s':>7} {'fail':>5}")
    print("-" * 64)
    summary = []
    for model in models:
        got = [r for r in rows if r["model"] == model and r["error"] == ""]
        failed = sum(1 for r in rows if r["model"] == model and r["error"])
        if not got:
            print(f"{model:<32} {'—':>6} {'—':>9} {'—':>7} {failed:>5}")
            continue
        accs = sorted(float(r["accuracy"]) for r in got)
        lats = sorted(float(r["latency_s"]) for r in got)
        acc = sum(accs) / len(accs)
        inv = sum(int(r["invented"]) for r in got)
        p50 = lats[len(lats) // 2]
        coverage = len(got) / max(1, len(got) + failed)
        summary.append((round(coverage, 2), -inv, round(acc, 3), -p50, model))
        print(f"{model:<32} {acc:>5.0%} {inv:>9} {p50:>7.2f} {failed:>5}")

    if summary:
        summary.sort(reverse=True)
        best = summary[0]
        print(f"\nwinner: {best[4]}  (couverture {best[0]:.0%}, "
              f"inventés {-best[1]}, exactitude {best[2]:.0%})")
        weak = [row for row in summary if row[0] < 1.0]
        if weak:
            print("couverture incomplète, non comparable au reste: "
                  + ", ".join(f"{row[4]} {row[0]:.0%}" for row in weak))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["text", "image"], default="text")
    ap.add_argument("--models", help="comma-separated override of the candidate list")
    ap.add_argument("--cases", help="comma-separated case ids; default is the whole dataset")
    ap.add_argument("--sleep", type=float, default=5.0, help="seconds between calls (free-tier rate limits)")
    args = ap.parse_args()

    cases = load_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
        cases = [c for c in cases if c["id"] in wanted]
        if not cases:
            ap.error(f"--cases matched nothing (wanted: {sorted(wanted)})")
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        models = GEMINI_VISION if args.mode == "image" else GEMINI_TEXT + GROQ_TEXT

    images = render_images(cases) if args.mode == "image" else {}

    csv_path = results_path(f"models-{args.mode}", "csv")
    rows: List[dict] = []

    # Written per row, not at the end: a rate-limited run against a dozen free-tier
    # models takes long enough that an interrupted one must not lose everything.
    csv_file = open(csv_path, "w", encoding="utf-8", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=[
        "model", "case", "accuracy", "latency_s", "invented", "expected_nulls", "wrong_fields", "error",
    ])
    writer.writeheader()
    csv_file.flush()

    for model in models:
        engine = engine_for(model)
        print(f"\n=== {model} ({args.mode}) ===", flush=True)
        for case in cases:
            row = _run_case(engine, model, case, images.get(case["id"]), args.sleep, csv_file, writer)
            rows.append(row)

    csv_file.close()

    _print_leaderboard(models, rows)
    print(f"csv: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
