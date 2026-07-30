#!/usr/bin/env python3
"""Fail if fr / en / ar drift apart.

`fr` is the reference and the fallback. A key added to fr but missing from ar
renders the raw key ("settings.confidence") to anyone using that language, and
nothing in the type system notices.

Stdlib only:  python scripts/check_locales.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Set

LOCALES = Path(__file__).resolve().parents[1] / "Dashboard" / "src" / "locales"
REFERENCE = "fr"


def flatten(obj, prefix: str = "") -> Set[str]:
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys |= flatten(v, f"{prefix}{k}.")
    else:
        keys.add(prefix.rstrip("."))
    return keys


def main() -> int:
    files = sorted(LOCALES.glob("*.json"))
    if not files:
        print(f"no locale files under {LOCALES}")
        return 1

    sets = {}
    for f in files:
        try:
            sets[f.stem] = flatten(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            print(f"{f.name} is not valid JSON: {exc}")
            return 1

    if REFERENCE not in sets:
        print(f"missing reference locale {REFERENCE}.json")
        return 1

    ref = sets[REFERENCE]
    problems = []
    for name, keys in sorted(sets.items()):
        if name == REFERENCE:
            continue
        for k in sorted(ref - keys):
            problems.append(f"{name}.json is missing '{k}' (present in {REFERENCE})")
        for k in sorted(keys - ref):
            problems.append(f"{name}.json has extra '{k}' (absent from {REFERENCE})")

    if problems:
        print(f"{len(problems)} locale key problem(s)\n")
        for p in problems:
            print("  " + p)
        return 1

    print(f"Locales in sync ({len(ref)} keys x {len(sets)} languages).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
