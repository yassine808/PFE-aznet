"""Merge the API run and the local GPU run into one pair of review files.

run_compare.py produces results/compare_*.csv  (groq, gemini, hf-darija)
run_local.py   produces results/local_*.csv    (the downloaded checkpoints)

Both use the same columns, so they concatenate. This writes:

    results/comparison.csv   every engine x every clip, one row each
    results/comparison.md    grouped BY CLIP -- the file to read while
                             replaying the audio

Usage (either venv works, stdlib only):
    .venv-local/Scripts/python.exe build_comparison.py
    .venv-local/Scripts/python.exe build_comparison.py --api results/compare_X.csv --local results/local_Y.csv
"""
import argparse
import csv
import glob
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

RESULTS = Path(__file__).resolve().parent / "results"
COLUMNS = ["file", "provider", "latency_s", "confidence", "chars", "transcript", "error"]

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# One Gemini transcript hit 222_797 characters (a repetition loop), well past
# csv's 131_072 default field cap.
csv.field_size_limit(10 ** 8)

ARABIC = re.compile(r"[؀-ۿ]")
DIGIT = re.compile(r"\d")
# Latin runs of 3+ letters: the French technical borrowings (goulotte, fibre,
# panneau) that must survive for the extraction chain to fill the Sheet.
LATIN_WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def latest(pattern: str) -> Optional[str]:
    hits = glob.glob(str(RESULTS / pattern))
    return max(hits, key=os.path.getmtime) if hits else None


def safe_csv(path: str) -> Path:
    """A `--api`/`--local` argument resolved, refused outside the repo.

    The paths come off the command line and are opened, so they are checked
    rather than trusted: this merges result CSVs, and a `../..` in one of them
    should not turn it into a reader of arbitrary files.
    """
    root = Path(__file__).resolve().parent.parent
    target = Path(path) if Path(path).is_absolute() else root / path
    target = target.resolve()
    if root not in target.parents:
        raise SystemExit(f"CSV paths must stay inside {root}, got {target}")
    return target


def read(path: str) -> List[dict]:
    with open(safe_csv(path), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def collect(api_files: List[str], local_files: List[str]) -> List[dict]:
    """Every run merged, later files winning per (engine, clip).

    A single-model rerun writes its own local_*.csv, so taking only the newest
    FILE would silently drop the other twelve engines. Read every run oldest
    first and let later rows overwrite earlier ones per (engine, clip) — so a
    rerun supersedes its own previous result and nothing else.
    """
    newest: dict = {}
    for path in api_files + local_files:
        if not path:
            continue
        got = read(path)
        for r in got:
            newest[(r["provider"], r["file"])] = r
        print(f"{Path(path).name}  ({len(got)} rows)")
    return list(newest.values())


def summarise(rows: List[dict]) -> list:
    """One tuple per engine: counts, mean latency and confidence, text shape."""
    summary = []
    for name in sorted({r["provider"] for r in rows}):
        rs = [r for r in rows if r["provider"] == name]
        ok = [r for r in rs if not r["error"]]
        if not ok:
            summary.append((name, len(rs), 0, None, None, 0, 0, 0))
            continue
        lat = [float(r["latency_s"]) for r in ok if r["latency_s"]]
        conf = [float(r["confidence"]) for r in ok if r["confidence"]]
        text = "".join(r["transcript"] or "" for r in ok)
        summary.append((
            name, len(rs), len(ok),
            sum(lat) / len(lat) if lat else None,
            sum(conf) / len(conf) if conf else None,
            len(text), len(DIGIT.findall(text)), len(set(LATIN_WORD.findall(text))),
        ))
    return summary


def engine_table(summary: list) -> List[str]:
    """The per-engine table, best coverage first."""
    lines = []
    for name, n, ok, lat, conf, chars, digits, latin in sorted(
        summary, key=lambda t: (-t[2], t[0])
    ):
        lines.append(
            f"| `{name}` | {n} | {ok} | "
            f"{'—' if lat is None else f'{lat:.1f} s'} | "
            f"{'—' if conf is None else f'{conf:.3f}'} | "
            f"{chars} | {digits} | {latin} |"
        )
    return lines


def clip_sections(by_file: dict) -> List[str]:
    """Every clip with each engine's transcript under it, for reading side by side."""
    lines: List[str] = []
    for fname in sorted(by_file):
        lines += [f"### {fname}", ""]
        for r in sorted(by_file[fname], key=lambda r: r["provider"]):
            if r["error"]:
                lines.append(f"- **{r['provider']}** — ERROR: `{r['error']}`")
                continue
            t = r["transcript"] or ""
            conf = "n/a" if not r["confidence"] else f"{float(r['confidence']):.3f}"
            lines += [
                f"- **{r['provider']}** — {r['latency_s']}s · confidence {conf} · "
                f"{len(t)} chars · {len(DIGIT.findall(t))} digits",
                "",
                f"  > {t if t else '(EMPTY)'}",
                "",
            ]
        lines.append("")
    return lines


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default=None, help="compare_*.csv (default: newest)")
    p.add_argument("--local", default=None, nargs="*",
                   help="local_*.csv files (default: newest per engine)")
    args = p.parse_args()

    if args.local:
        local_files = list(args.local)
    else:
        local_files = sorted(glob.glob(str(RESULTS / "local_*.csv")), key=os.path.getmtime)
    api_files = [args.api] if args.api else sorted(
        glob.glob(str(RESULTS / "compare_*.csv")), key=os.path.getmtime)

    rows: List[dict] = collect(api_files, local_files)
    if not rows:
        raise SystemExit("nothing to merge")

    RESULTS.mkdir(exist_ok=True)
    out_csv = RESULTS / "comparison.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    engines = sorted({r["provider"] for r in rows})
    lines = [
        "# STT comparison — listen to each clip, then judge the transcripts",
        "",
        "Merged from the API run and the local GPU run. Every engine saw the same",
        "11 real WhatsApp clips (603 s of Darija).",
        "",
        "## What to judge, in priority order",
        "",
        "1. **Quantities** — `ربعين` (40), `تمنية` (8), `طناشر` (12), or digits.",
        "   Wrong numbers are the one failure the Sheet cannot survive.",
        "2. **French technical terms** — goulotte, fibre, panneau de brassage,",
        "   éclairage. Do they survive as recognisable words?",
        "3. **Names** — chantier (Novec, Essaouira, Kenitra) and people.",
        "",
        "**Confidence is not comparable across families.** Whisper reports",
        "`exp(mean logprob)`, wav2vec2 reports mean CTC softmax, Gemini reports",
        "nothing (`n/a` — never 0). Compare within a family only, and note that",
        "in this dataset confidence has repeatedly failed to track correctness.",
        "",
        "## Per engine",
        "",
        "| engine | clips | ok | mean latency | mean conf | total chars | digits | distinct Latin words |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += engine_table(summarise(rows))
    lines += ["", "`—` in the confidence column means the engine exposes no usable "
                  "signal. It is never a score of zero.", ""]

    # --- per clip, every engine side by side --------------------------------
    lines += ["## Clip by clip", ""]
    by_file: dict = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)
    lines += clip_sections(by_file)

    out_md = RESULTS / "comparison.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{len(engines)} engines x {len(by_file)} clips = {len(rows)} rows")
    print(f"Saved: {out_csv}\n       {out_md}")


if __name__ == "__main__":
    main()
