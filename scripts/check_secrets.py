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
# Matches any identifier assignment; the keyword check happens in Python
# (looks_like_secret_name) rather than in the regex, so there is no
# quantifier-then-alternation backtracking risk on adversarial input.
ASSIGNMENT = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(["']?)([^\s"',;)]{6,})\2""",
)

SECRET_NAME_KEYWORDS = (
    "SECRET", "PASSWORD", "PASSWD", "TOKEN", "APIKEY", "ACCESSKEY",
    "PRIVATEKEY", "CREDENTIAL", "AUTH",
)

# Prefixes/whole-value markers that mean "this is a placeholder", checked with
# plain string ops instead of `.*x.*y.*`-shaped regexes (superlinear on long lines).
PLACEHOLDER_SUBSTRINGS = ("${", "{{", "}}", "xxx", "...", "***")
PLACEHOLDER_WHOLE_VALUES = {
    "changeme", "placeholder", "none", "null", "true", "false", "undefined",
}
PLACEHOLDER_PREFIXES = (
    "your", "your-", "your_", "my-", "my_", "some-", "some_", "the-", "the_",
    "example", "dummy", "test", "fake", "sample",
    "process.env", "os.environ", "env.", "settings.",
)
PLACEHOLDER_RE = re.compile(r"^(<.*>|\$[a-z_.]+)$", re.IGNORECASE)

# Values that are structurally code or prose, not credentials.
NOT_A_SECRET_WHOLE_RE = re.compile(
    r"^([a-z]+(?:[-_][a-z]+)*|\d+|str|int|bool|float)$", re.IGNORECASE
)
NOT_A_SECRET_PREFIXES = ("create",)
NOT_A_SECRET_SUFFIXES = (".py", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml")


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


def looks_like_secret_name(name: str) -> bool:
    normalized = name.upper().replace("_", "").replace("-", "")
    return any(kw in normalized for kw in SECRET_NAME_KEYWORDS)


def is_placeholder(value: str) -> bool:
    if not value:
        return True
    low = value.lower()
    if any(s in low for s in PLACEHOLDER_SUBSTRINGS):
        return True
    if low in PLACEHOLDER_WHOLE_VALUES:
        return True
    if low.startswith(PLACEHOLDER_PREFIXES):
        return True
    if PLACEHOLDER_RE.match(value):
        return True
    if NOT_A_SECRET_WHOLE_RE.match(value):
        return True
    if low.startswith(NOT_A_SECRET_PREFIXES) or low.endswith(NOT_A_SECRET_SUFFIXES):
        return True
    return "(" in value or "/" in value


def _pattern_findings(path: str, lineno: str, line: str) -> List[str]:
    findings = []
    for label, pat in PATTERNS:
        m = re.search(pat, line)
        # A marker inside backticks is documentation quoting the shape of a
        # credential ("starts with `-----BEGIN PRIVATE KEY-----`"), not one.
        if m and not (line[: m.start()].endswith("`") or line[m.end() :].startswith("`")):
            findings.append(f"{path}:{lineno}: {label} -> {m.group(0)[:24]}...")
    return findings


def _assignment_finding(path: str, lineno: str, line: str) -> str | None:
    m = ASSIGNMENT.search(line)
    if not m:
        return None
    name, value = m.group(1), m.group(3)
    if not looks_like_secret_name(name):
        return None
    if is_placeholder(value) or not looks_like_credential(value):
        return None
    return f"{path}:{lineno}: hardcoded {name} -> {value[:16]}..."


def scan(path: str) -> List[str]:
    p = ROOT / path
    if p.suffix.lower() in SKIP_SUFFIXES or path in SKIP_PATHS:
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:  # minified bundle or embedded blob
            continue
        findings.extend(_pattern_findings(path, str(lineno), line))
        assignment_finding = _assignment_finding(path, str(lineno), line)
        if assignment_finding:
            findings.append(assignment_finding)
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
