"""Darija STT benchmark harness (PLAN.md Sprint 1).

Runs every STT adapter over dataset/audio/, scores WER/CER against
references.csv, optionally runs LLM extraction and scores field accuracy.

Usage (from benchmark/, with the api venv):
    ../api/.venv/Scripts/python.exe run_benchmark.py --dry-run
    ../api/.venv/Scripts/python.exe run_benchmark.py
    ../api/.venv/Scripts/python.exe run_benchmark.py --providers groq,gemini --no-extraction
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))            # metrics.py
sys.path.insert(0, str(BENCH_DIR.parent / "api"))  # app package

from metrics import extraction_accuracy, wer_cer  # noqa: E402

DATASET = BENCH_DIR / "dataset"
AUDIO_DIR = DATASET / "audio"
REFERENCES = DATASET / "references.csv"
RESULTS_DIR = BENCH_DIR / "results"

MIME_TYPES = {".ogg": "audio/ogg", ".opus": "audio/ogg", ".mp3": "audio/mpeg",
              ".wav": "audio/wav", ".m4a": "audio/mp4"}
NOISE_LEVELS = {"quiet", "street", "echo"}

RESULT_COLUMNS = ["file", "provider", "wer", "cer", "latency_s",
                  "extraction_acc", "field_detail", "hypothesis", "error"]


def _validate_row(row: dict, i: int) -> List[str]:
    """Structural checks for one references.csv row. Returns problem strings."""
    if not (row.get("file") or "").strip():
        return [f"line {i}: empty 'file'"]

    problems = []
    audio = AUDIO_DIR / row["file"]
    if not audio.exists():
        problems.append(f"line {i}: {audio.name} missing from dataset/audio/")
    if audio.suffix.lower() not in MIME_TYPES:
        problems.append(f"line {i}: unsupported extension {audio.suffix}")
    if row.get("noise") not in NOISE_LEVELS:
        problems.append(f"line {i}: noise must be one of {sorted(NOISE_LEVELS)}")
    if not (row.get("reference_transcription") or "").strip():
        problems.append(f"line {i}: empty reference_transcription")
    try:
        expected = json.loads(row.get("expected_json") or "")
        if not isinstance(expected, dict) or not expected:
            problems.append(f"line {i}: expected_json must be a non-empty JSON object")
    except json.JSONDecodeError as exc:
        problems.append(f"line {i}: expected_json is not valid JSON ({exc})")
    return problems


def load_references() -> List[dict]:
    """Read and validate references.csv. Raises on structural problems."""
    if not REFERENCES.exists():
        raise FileNotFoundError(f"{REFERENCES} not found")
    with open(REFERENCES, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("references.csv has a header but no data rows — record the dataset first (see README.md)")

    problems = []
    for i, row in enumerate(rows, start=2):  # line numbers incl. header
        problems.extend(_validate_row(row, i))
    if problems:
        raise ValueError("references.csv validation failed:\n  " + "\n  ".join(problems))
    return rows


def run(providers: List[str], with_extraction: bool) -> List[dict]:
    from app.providers import get_provider
    from app.providers.base import TranscriptionError

    rows = load_references()
    results = []
    for row in rows:
        audio_path = AUDIO_DIR / row["file"]
        blob = audio_path.read_bytes()
        mime = MIME_TYPES[audio_path.suffix.lower()]
        expected = json.loads(row["expected_json"])

        for name in providers:
            record = dict.fromkeys(RESULT_COLUMNS)
            record.update({"file": row["file"], "provider": name})
            try:
                info = get_provider(name).transcribe(blob, mime)
                record["hypothesis"] = info.text
                record["latency_s"] = round(info.latency_s, 2)
                record["wer"], record["cer"] = (
                    round(v, 4) for v in wer_cer(row["reference_transcription"], info.text)
                )
                if with_extraction:
                    from app import extraction
                    report = extraction.extract_report(info.text)
                    acc, detail = extraction_accuracy(expected, report.model_dump())
                    record["extraction_acc"] = round(acc, 4)
                    record["field_detail"] = json.dumps(detail, ensure_ascii=False)
            except Exception as exc:  # record and continue, one bad call must not kill the run  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"
                print(f"  !! {row['file']} × {name}: {record['error']}")
            results.append(record)
            status = record["error"] or f"WER {record['wer']}  CER {record['cer']}  {record['latency_s']}s"
            print(f"  {row['file']} × {name}: {status}")
    return results


def summarize(results: List[dict]) -> None:
    print("\n=== Summary per engine ===")
    print(f"{'engine':<12}{'files':>6}{'errors':>8}{'mean WER':>10}{'mean CER':>10}{'mean lat':>10}{'extr acc':>10}")
    providers = sorted({r["provider"] for r in results})
    for name in providers:
        rows = [r for r in results if r["provider"] == name]
        ok = [r for r in rows if r["error"] is None]

        def mean(key: str) -> str:
            vals = [r[key] for r in ok if r[key] is not None]
            return f"{sum(vals) / len(vals):.3f}" if vals else "—"

        print(f"{name:<12}{len(rows):>6}{len(rows) - len(ok):>8}"
              f"{mean('wer'):>10}{mean('cer'):>10}{mean('latency_s'):>10}{mean('extraction_acc'):>10}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="validate references.csv and audio files, no API calls")
    parser.add_argument("--providers", default=None,
                        help="comma-separated engine names (default: all registered)")
    parser.add_argument("--no-extraction", action="store_true",
                        help="skip the LLM extraction step (WER/CER + latency only)")
    args = parser.parse_args()

    if args.dry_run:
        rows = load_references()
        print(f"OK — {len(rows)} rows valid, all audio files present.")
        return

    from app.providers import available_providers
    providers = args.providers.split(",") if args.providers else available_providers()
    print(f"Engines: {providers} | extraction: {not args.no_extraction}\n")

    results = run(providers, with_extraction=not args.no_extraction)
    summarize(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"results_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
