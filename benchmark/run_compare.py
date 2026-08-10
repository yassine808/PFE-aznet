"""Ground-truth-free STT comparison (TO-DO: finish the STT benchmark).

run_benchmark.py scores WER/CER/extraction against references.csv. This script
does the opposite: it makes no claim about correctness at all. It walks
dataset/audio/, runs every requested engine over every clip, and writes what
each one heard, how long it took, and what confidence it reports.

The ranking is done by a human listening to the clip and reading the three
transcripts side by side -- which, for 11 Darija clips, is more direct evidence
than a WER computed against a reference whose spelling convention neither
engine agreed to. Nothing here invents a score.

Usage (from benchmark/, with the api venv):
    ../api/.venv/Scripts/python.exe run_compare.py --list
    ../api/.venv/Scripts/python.exe run_compare.py
    ../api/.venv/Scripts/python.exe run_compare.py --providers groq,gemini
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import List

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR.parent / "api"))  # app package

# Transcripts are Arabic script; the Windows console defaults to cp1252 and
# raises UnicodeEncodeError on the first Darija word. Files are already written
# as UTF-8 -- this only fixes what is printed live.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DATASET = BENCH_DIR / "dataset"
AUDIO_DIR = DATASET / "audio"
RESULTS_DIR = BENCH_DIR / "results"

# Same table as run_benchmark.py; kept local rather than imported because that
# module refuses to load without a populated references.csv.
OGG = "audio/ogg"
MIME_TYPES = {".ogg": OGG, ".opus": OGG, ".oga": OGG,
              ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}

COLUMNS = ["file", "provider", "latency_s", "confidence", "chars", "transcript", "error"]


def find_clips() -> List[Path]:
    if not AUDIO_DIR.exists():
        raise FileNotFoundError(f"{AUDIO_DIR} not found")
    clips = sorted(p for p in AUDIO_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in MIME_TYPES)
    if not clips:
        raise ValueError(f"no supported audio in {AUDIO_DIR} "
                         f"(looked for {sorted(MIME_TYPES)})")
    return clips


def transcribe_one(name: str, clip: Path, blob: bytes, mime: str) -> dict:
    """One engine on one clip, as a result row. Never raises.

    One bad engine must not kill the run: a failure becomes an `error` cell so
    the comparison still shows what the other twelve heard.
    """
    from app.providers import get_provider

    record = dict.fromkeys(COLUMNS)
    record.update({"file": clip.name, "provider": name})
    try:
        info = get_provider(name).transcribe(blob, mime)
        record["transcript"] = info.text
        record["chars"] = len(info.text)
        record["latency_s"] = round(info.latency_s, 2)
        # None means "this engine exposes no usable signal" -- never 0,
        # never a made-up number. gemini is always None by design.
        record["confidence"] = (
            round(info.confidence, 4) if info.confidence is not None else None
        )
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def run(clips: List[Path], providers: List[str]) -> List[dict]:
    results = []
    for clip in clips:
        blob = clip.read_bytes()
        mime = MIME_TYPES[clip.suffix.lower()]
        print(f"\n{clip.name}  ({len(blob) / 1024:.0f} KB)")
        for name in providers:
            record = transcribe_one(name, clip, blob, mime)
            results.append(record)
            if record["error"]:
                print(f"  {name:<12} !! {record['error']}")
            else:
                conf = "—" if record["confidence"] is None else f"{record['confidence']:.3f}"
                print(f"  {name:<12} {record['latency_s']:>6.2f}s  conf {conf:>6}  "
                      f"{record['transcript'][:70]}")
    return results


def summarize(results: List[dict]) -> None:
    print("\n=== Per engine ===")
    print(f"{'engine':<14}{'clips':>6}{'errors':>8}{'mean lat':>10}{'mean conf':>11}{'mean chars':>12}")
    for name in sorted({r["provider"] for r in results}):
        rows = [r for r in results if r["provider"] == name]
        ok = [r for r in rows if r["error"] is None]

        def mean(key: str, fmt: str) -> str:
            vals = [r[key] for r in ok if r[key] is not None]
            return format(sum(vals) / len(vals), fmt) if vals else "—"

        print(f"{name:<14}{len(rows):>6}{len(rows) - len(ok):>8}"
              f"{mean('latency_s', '.2f'):>10}{mean('confidence', '.3f'):>11}"
              f"{mean('chars', '.0f'):>12}")
    print("\nmean conf '—' = engine exposes no confidence signal (not a zero score).")


def write_sidebyside(results: List[dict], path: Path) -> None:
    """Markdown grouped by clip -- the file you read while replaying the audio."""
    by_file: dict = {}
    for r in results:
        by_file.setdefault(r["file"], []).append(r)
    lines = ["# STT comparison — listen to each clip, judge the transcripts", ""]
    for fname, rows in by_file.items():
        lines += [f"## {fname}", ""]
        for r in rows:
            if r["error"]:
                lines.append(f"- **{r['provider']}** — ERROR: {r['error']}")
                continue
            conf = "n/a" if r["confidence"] is None else f"{r['confidence']:.3f}"
            lines += [f"- **{r['provider']}** — {r['latency_s']}s · confidence {conf} "
                      f"· {r['chars']} chars", "", f"  > {r['transcript']}", ""]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true",
                        help="show clips and registered engines, make no calls")
    parser.add_argument("--providers", default=None,
                        help="comma-separated engine names (default: all registered)")
    args = parser.parse_args()

    from app.providers import available_providers

    clips = find_clips()
    providers = args.providers.split(",") if args.providers else available_providers()

    if args.list:
        print(f"{len(clips)} clips in {AUDIO_DIR}:")
        for c in clips:
            print(f"  {c.name}  ({c.stat().st_size / 1024:.0f} KB)")
        print(f"\nregistered engines: {available_providers()}")
        return

    print(f"{len(clips)} clips × {len(providers)} engines = {len(clips) * len(providers)} calls")
    print(f"engines: {providers}")

    results = run(clips, providers)
    summarize(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    csv_path = RESULTS_DIR / f"compare_{stamp}.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    md_path = RESULTS_DIR / f"compare_{stamp}.md"
    write_sidebyside(results, md_path)
    print(f"\nSaved: {csv_path}\n       {md_path}")


if __name__ == "__main__":
    main()
