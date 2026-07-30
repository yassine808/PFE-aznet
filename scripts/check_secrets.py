#!/usr/bin/env python3
"""Fail the build if a credential is committed.

Scans git-tracked files only — an untracked .env is not a leak, and scanning
the working tree would flag the developer's own local secrets on every run.

Stdlib only and no network, so it runs identically in CI and on a laptop:
    python scripts/check_secrets.py

Two kinds of rule:
  * PATTERNS — shaped credentials (JWT, Google keys, Slack/GitHub tokens...).
  * ASSIGNMENTS — a secret-ish name assigned a literal. This is the one that
    catches project-specific slips, e.g. a token pasted into the n8n workflow
    instead of read from $env.

Anything that is provably a placeholder (empty, ${...}, {{...}}, <...>, xxx,
changeme, your-key-here) is not a finding — .env.example exists to hold those.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Files we never scan: lockfiles are noise, this script is all false positives.
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf"}
SKIP_PATHS = {
    "scripts/check_secrets.py",
    "package-lock.json",
    "Dashboard/package-lock.json",
}

PATTERNS: List[Tuple[str, str]] = [
    ("AWS access key id", r"AKIA[0-9A-Z]{16}"),
    ("Google API key", r"AIza[0-9A-Za-z_\-]{35}"),
    ("Google OAuth client secret", r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    ("Slack token", r"xox[abprs]-[0-9A-Za-z\-]{10,}"),
    ("GitHub token", r"gh[pousr]_[0-9A-Za-z]{36,}"),
    ("OpenAI-style key", r"sk-[A-Za-z0-9]{20,}"),
    ("Groq key", r"gsk_[A-Za-z0-9]{20,}"),
    ("Telegram bot token", r"\b\d{8,10}:AA[0-9A-Za-z_\-]{33}"),
    ("JWT", r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("Private key block", r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
]

# name = "literal"  /  name: 'literal'  /  NAME=literal
ASSIGNMENT = re.compile(
    r"""(?i)\b([A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|
        PRIVATE[_-]?KEY|CREDENTIAL|AUTH)[A-Z0-9_]*)\s*[:=]\s*(["']?)([^\s"',;)]{6,})\2""",
    re.VERBOSE,
)

PLACEHOLDER = re.compile(
    r"""(?ix)
    ^(
      .*\$\{.*\}.* | .*\{\{.*\}\}.* | <.*> | \$[a-z_.]+ |  # interpolation / $env.X
      (your|my|some|the)[-_]?.* |                          # your-key-here
      .*x{3,}.* | .*\.{3,}.* | .*\*{3,}.* | changeme | placeholder |
      example.* | dummy.* | test.* | fake.* | sample.* |
      none | null | true | false | undefined |
      process\.env.* | os\.environ.* | env\..* | settings\..*
    )$""",
)

# Values that are structurally code or prose, not credentials.
NOT_A_SECRET = re.compile(
    r"""(?ix)^(
      [a-z]+([-_][a-z]+)* |     # bare identifier / hyphenated prose: session-based
      [0-9]+ |                  # a number: timeout = 300
      [a-z_]+\.[a-z_]+\(.* |    # a call: secrets.token_urlsafe(32)
      create[A-Z].* | /.* | .*\(.* | .*/.* |
      (str|int|bool|float|Optional.*|List.*|Field.*) |
      .*\.(py|ts|tsx|json|md|yml|yaml)
    )$""",
)


def looks_like_credential(value: str) -> bool:
    """A real credential is long, dense and mixes character classes.

    Without this the assignment rule flags every `token = value` in ordinary
    code, and a check that cries wolf gets disabled within a week.
    """
    if len(value) < 12:
        return False
    if any(c.isspace() or c in "`\"'" for c in value):
        return False
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def tracked_files() -> List[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [f for f in out.splitlines() if f]


def is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.match(value) or NOT_A_SECRET.match(value))


def scan(path: str) -> List[str]:
    p = ROOT / path
    if p.suffix.lower() in SKIP_SUFFIXES or path in SKIP_PATHS:
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, IsADirectoryError):
        return []

    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:  # minified bundle or embedded blob
            continue
        for label, pat in PATTERNS:
            m = re.search(pat, line)
            # A marker inside backticks is documentation quoting the shape of a
            # credential ("starts with `-----BEGIN PRIVATE KEY-----`"), not one.
            if m and not (line[: m.start()].endswith("`") or line[m.end() :].startswith("`")):
                findings.append(f"{path}:{lineno}: {label} -> {m.group(0)[:24]}...")
        m = ASSIGNMENT.search(line)
        if m:
            name, value = m.group(1), m.group(3)
            if not is_placeholder(value) and looks_like_credential(value):
                findings.append(f"{path}:{lineno}: hardcoded {name} -> {value[:16]}...")
    return findings


def main() -> int:
    findings = []
    for f in tracked_files():
        findings.extend(scan(f))

    if findings:
        print("Committed credentials found:\n")
        for f in findings:
            print("  " + f)
        print(
            "\nMove the value to the environment and read it via $env (n8n), "
            "settings (api) or import.meta.env (Dashboard).\n"
            "A genuine false positive belongs in SKIP_PATHS or the placeholder rule."
        )
        return 1

    print(f"No committed credentials found ({len(tracked_files())} tracked files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
