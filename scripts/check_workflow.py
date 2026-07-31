#!/usr/bin/env python3
"""Validate n8n/aznet-complete.json before it reaches n8n.

n8n only reports a bad expression at runtime, on the node that uses it — which
on 2026-07-30 meant a technician's WhatsApp message died at `WA reply summary`
with "invalid syntax" and no reply, no Sheet row and no log entry (the log node
sits downstream of the reply). These are the mistakes that produced that, made
cheap to catch:

  * a raw newline inside a single-quoted string in an expression — terminates
    the literal; must be written as the two characters backslash + n
  * unbalanced quotes in an expression
  * a hardcoded token where $env belongs

Stdlib only:  python scripts/check_workflow.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, List

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "n8n" / "aznet-complete.json"

EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)
SECRET_LITERAL = re.compile(
    r"(?i)(bot|api|access|verify)?[_-]?token[\"']?\s*[:=]\s*[\"']?"
    r"(?!\s*=?\s*\{\{|\$env|\$json)([A-Za-z0-9_\-]{20,})"
)


def walk_strings(node: Any, path: str = ""):
    """Yield every (json-path, string) pair, so no parameter shape is missed."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")


def check_node(node: dict) -> List[str]:
    name = node.get("name", "?")
    problems = []
    for path, value in walk_strings(node.get("parameters", {})):
        for expr in EXPR.findall(value):
            if "\n" in expr:
                problems.append(
                    f"{name}{path}: raw newline inside an expression — write "
                    r"it as \n (backslash + n), a real newline ends the string literal"
                )
            if expr.count("'") % 2:
                problems.append(f"{name}{path}: unbalanced single quotes in expression")
            if expr.count('"') % 2:
                problems.append(f"{name}{path}: unbalanced double quotes in expression")
        m = SECRET_LITERAL.search(value)
        if m:
            problems.append(f"{name}{path}: hardcoded token {m.group(2)[:12]}... — use $env")
    return problems


def _check_connections(wf: dict, names: set) -> List[str]:
    """Every connection must point at a node that exists — a rename that misses
    one edge leaves a branch that silently never runs.
    """
    problems: List[str] = []
    for src, conn in (wf.get("connections") or {}).items():
        if src not in names:
            problems.append(f"connection from unknown node {src!r}")
        for branch in conn.get("main", []):
            for edge in branch or []:
                if edge.get("node") not in names:
                    problems.append(f"{src} -> unknown node {edge.get('node')!r}")
    return problems


def main() -> int:
    if not WORKFLOW.exists():
        print(f"{WORKFLOW} not found")
        return 1
    try:
        wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{WORKFLOW.name} is not valid JSON: {exc}")
        return 1

    nodes = wf.get("nodes", [])
    problems: List[str] = []
    for node in nodes:
        problems.extend(check_node(node))

    names = {n.get("name") for n in nodes}
    problems.extend(_check_connections(wf, names))

    if problems:
        print(f"{WORKFLOW.name}: {len(problems)} problem(s)\n")
        for p in problems:
            print("  " + p)
        return 1

    print(f"{WORKFLOW.name} OK ({len(nodes)} nodes, expressions parse, no hardcoded tokens).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
