"""Diff the LIVE n8n workflow against n8n/aznet-complete.json — read only.

CLAUDE.md's warning runs in both directions. Everyone remembers that editing
the repo file changes nothing until it is re-imported; the mirror image is
worse — a UI edit never exported leaves the repo describing a pipeline that no
longer exists, and a well-meaning push silently reverts it.

So: look before writing. This script writes nothing to n8n and nothing to the
repo. It prints which nodes exist only live, only in the file, and which differ
in parameters — after filtering the documented noise:

  * n8n strips its own defaults (`resource`, `httpMethod`, `outputPropertyName`)
  * n8n adds `"version": 1` to IF conditions
  * position/id churn is not behaviour

Credentials are read from the environment or .env and NEVER printed.

    python n8n/diff_live.py
    python n8n/diff_live.py --save live-export.json
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "n8n" / "aznet-complete.json"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

NOISE_KEYS = {"resource", "httpMethod", "outputPropertyName"}


def env(name: str) -> str:
    """Environment first, then .env. The value is used, never echoed."""
    if os.environ.get(name):
        return os.environ[name]
    for candidate in (ROOT / ".env", ROOT / "Dashboard" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def fetch(base: str, key: str) -> list:
    url = base.rstrip("/") + "/api/v1/workflows?limit=250"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", [])


def strip(params: dict) -> dict:
    """Drop the differences n8n creates by itself, so real edits stand out."""
    out = {}
    for k, v in (params or {}).items():
        if k in NOISE_KEYS:
            continue
        if k == "conditions" and isinstance(v, dict):
            v = {kk: vv for kk, vv in v.items() if kk != "version"}
        out[k] = v
    return out


def safe_out_path(raw: str) -> Path:
    """`--save` resolved, refused if it points outside the repo.

    The path comes off the command line and is written to, so it is checked
    rather than trusted: a `../..` in it would drop a workflow dump — API key
    URLs and all — somewhere nobody thinks to look.
    """
    root = Path(__file__).resolve().parent.parent
    target = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if root not in target.parents:
        raise SystemExit(f"--save must stay inside {root}, got {target}")
    return target


def pick_live(workflows: list, local_names: set):
    """The live workflow sharing the most node names with the repo file.

    Matched on overlap rather than on name: the workflow gets renamed in the UI
    far more often than its node set changes.
    """
    best, best_score = None, -1
    for w in workflows:
        names = {n["name"] for n in (w.get("nodes") or [])}
        score = len(names & local_names)
        if score > best_score:
            best, best_score = w, score
    return best, best_score


def report_nodes(rn: dict, ln: dict) -> None:
    """The three node-set differences, printed."""
    only_live = sorted(set(rn) - set(ln))
    only_file = sorted(set(ln) - set(rn))
    both = sorted(set(rn) & set(ln))

    print(f"\n=== ONLY LIVE ({len(only_live)}) — in n8n, missing from the repo file ===")
    for n in only_live:
        print(f"  + {n}   [{rn[n]['type'].split('.')[-1]}]")
    print(f"\n=== ONLY IN FILE ({len(only_file)}) — pushing would ADD these ===")
    for n in only_file:
        print(f"  - {n}   [{ln[n]['type'].split('.')[-1]}]")

    changed = [n for n in both if strip(rn[n].get("parameters")) != strip(ln[n].get("parameters"))]
    print(f"\n=== PARAMETERS DIFFER ({len(changed)}) ===")
    for n in changed:
        print(f"  ~ {n}   [{rn[n]['type'].split('.')[-1]}]")


def writes_sheet(nodes) -> list:
    """The question that started this: who writes the Sheet?"""
    hits = []
    for n in nodes:
        blob = json.dumps(n.get("parameters", {}), ensure_ascii=False)
        if "googleSheets" in n.get("type", ""):
            hits.append(f"{n['name']} [googleSheets node]")
        if "/journal" in blob:
            hits.append(f"{n['name']} [POST /journal]")
    return hits


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--save", default=None, help="write the live workflow JSON here")
    args = p.parse_args()

    base = env("N8N_URL") or "http://localhost:5678"
    key = env("N8N_API_KEY") or env("VITE_N8N_API_KEY")
    if not key:
        raise SystemExit("no N8N_API_KEY found in environment, .env or Dashboard/.env")
    print(f"n8n base: {base}   (key loaded, not shown)")

    try:
        workflows = fetch(base, key)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"cannot reach n8n: {type(exc).__name__}: {exc}")

    print(f"{len(workflows)} workflow(s) live:")
    for w in workflows:
        print(f"  id={w.get('id')}  active={w.get('active')}  {w.get('name')!r} "
              f"({len(w.get('nodes') or [])} nodes)")

    local = json.loads(FILE.read_text(encoding="utf-8"))
    ln = {n["name"]: n for n in local["nodes"]}

    best, best_score = pick_live(workflows, set(ln))
    if not best:
        raise SystemExit("no workflow to compare against")

    print(f"\ncomparing against live id={best.get('id')} {best.get('name')!r} "
          f"(shares {best_score} node names)")
    if args.save:
        out = safe_out_path(args.save)
        out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved live workflow -> {out}")

    report_nodes({n["name"]: n for n in best.get("nodes") or []}, ln)

    print("\n=== WHO WRITES THE SHEET ===")
    print("  live:", writes_sheet(best.get("nodes") or []) or "nothing found")
    print("  file:", writes_sheet(local["nodes"]) or "nothing found")


if __name__ == "__main__":
    main()
