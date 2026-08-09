"""Push the reply-node patches to the LIVE workflow, and archive the rest.

Run diff_live.py first — this writes to n8n.

Two jobs, both deliberately narrow:

1. PUSH. Only the active workflow is updated, and only with the file whose diff
   you have already reviewed (2 nodes: TG/WA reply summary). The public API
   rejects `settings` keys it does not accept (binaryMode, availableInMCP -> 400)
   and silently keeps whatever it had, so the payload is trimmed to the four
   fields the API documents. RE-CHECK Settings -> Error Workflow afterwards:
   that setting lives in `settings` and is the one CLAUDE.md warns about.

2. ARCHIVE. The 22 inactive workflows are written to n8n/archive/*.json and
   left in place. Nothing is deleted — the archive is what makes deletion safe
   later, not a substitute for deciding to delete.

    python n8n/push_and_archive.py --archive-only
    python n8n/push_and_archive.py --push
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "n8n" / "aznet-complete.json"
ARCHIVE = ROOT / "n8n" / "archive"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# The API accepts only these on update; anything else is a 400 or is dropped.
ALLOWED = ("name", "nodes", "connections", "settings")


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for candidate in (ROOT / ".env", ROOT / "Dashboard" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def call(base: str, key: str, path: str, method: str = "GET", body=None):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:70] or "workflow"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--push", action="store_true", help="update the active workflow")
    p.add_argument("--archive-only", action="store_true", help="archive, do not push")
    args = p.parse_args()

    base = env("N8N_URL") or "http://localhost:5678"
    key = env("N8N_API_KEY") or env("VITE_N8N_API_KEY")
    if not key:
        raise SystemExit("no N8N_API_KEY found")
    print(f"n8n: {base}  (key loaded, not shown)")

    workflows = call(base, key, "/api/v1/workflows?limit=250").get("data", [])
    active = [w for w in workflows if w.get("active")]
    print(f"{len(workflows)} workflows, {len(active)} active")

    # --- archive every inactive one -------------------------------------
    ARCHIVE.mkdir(exist_ok=True)
    written = 0
    for w in workflows:
        if w.get("active"):
            continue
        out = ARCHIVE / f"{safe(w.get('name', ''))}--{w.get('id')}.json"
        out.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1
    print(f"archived {written} inactive workflow(s) -> {ARCHIVE.relative_to(ROOT)}/")

    if args.archive_only or not args.push:
        print("archive only — nothing pushed")
        return

    if len(active) != 1:
        raise SystemExit(f"expected exactly 1 active workflow, found {len(active)} — refusing to push")
    target = active[0]
    local = json.loads(FILE.read_text(encoding="utf-8"))

    # Safety: the file must match the target, or this is not the workflow the
    # reviewed diff described.
    live_names = {n["name"] for n in target.get("nodes") or []}
    file_names = {n["name"] for n in local["nodes"]}
    if live_names != file_names:
        raise SystemExit(
            f"node sets differ (live-only={sorted(live_names - file_names)}, "
            f"file-only={sorted(file_names - live_names)}) — refusing to push"
        )

    payload = {k: local[k] for k in ("nodes", "connections") if k in local}
    payload["name"] = target.get("name") or local.get("name")

    # `settings` is required on PUT, yet n8n RETURNS keys it will not ACCEPT:
    # echoing the live object back gives 400 "must NOT have additional
    # properties" (binaryMode, availableInMCP), and omitting it gives 400
    # "must have required property 'settings'". So: filter to the accepted
    # keys, taken from LIVE rather than from the repo file — the file carries
    # errorWorkflow:"" and pushing that would CLEAR the Error Workflow, the
    # exact setting CLAUDE.md says to re-check after every push.
    ACCEPTED_SETTINGS = {
        "executionOrder", "errorWorkflow", "timezone", "executionTimeout",
        "saveDataErrorExecution", "saveDataSuccessExecution",
        "saveExecutionProgress", "saveManualExecutions",
    }
    live_settings = target.get("settings") or {}
    kept = {k: v for k, v in live_settings.items() if k in ACCEPTED_SETTINGS}
    dropped = sorted(set(live_settings) - set(kept))
    payload["settings"] = kept
    print(f"settings kept: {sorted(kept)}   dropped (API rejects): {dropped}")
    if not kept.get("errorWorkflow"):
        print("  NOTE: errorWorkflow is empty on the live workflow — the Error "
              "Trigger will not fire until it is set in the UI.")

    call(base, key, f"/api/v1/workflows/{target['id']}", "PUT", payload)
    print(f"pushed -> id={target['id']} {target.get('name')!r}")
    print("NOW: n8n UI -> Settings -> Error Workflow must still point at this workflow.")


if __name__ == "__main__":
    main()
