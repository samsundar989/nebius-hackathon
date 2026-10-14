#!/usr/bin/env python3
"""Fail if staged (or given) files contain something that looks like a credential.

Used by .githooks/pre-commit and CI. Prints file:line and the rule, never the value.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RULES: list[tuple[str, re.Pattern[str]]] = [
    # An assignment of a non-empty value to one of our secret env vars.
    (
        "env-secret-assignment",
        re.compile(
            r"\b(NEBIUS_API_KEY|TAVILY_API_KEY|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*['\"]?[A-Za-z0-9._\-]{8,}"
        ),
    ),
    ("bearer-token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{40,}")),
    ("tavily-key", re.compile(r"\btvly-[A-Za-z0-9]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "long-opaque-token",
        re.compile(r"(?<![A-Za-z0-9/+_\-])[A-Za-z0-9_\-]{120,}(?![A-Za-z0-9/+_\-])"),
    ),
]
SKIP_SUFFIXES = {".png", ".jpg", ".gif", ".mp4", ".zip", ".lock"}
SKIP_NAMES = {"uv.lock", ".env.example"}
ALLOW_MARKER = "secret-scan: allow"


def staged_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [Path(p) for p in out.splitlines() if p]


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout
    return [Path(p) for p in out.splitlines() if p]


def scan(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            hits.append(f"{path}: env file must never be committed")
            continue
        if path.suffix in SKIP_SUFFIXES or path.name in SKIP_NAMES or not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            for rule, pattern in RULES:
                if pattern.search(line):
                    hits.append(f"{path}:{lineno}: {rule}")
    return hits


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--all":
        paths = tracked_files()
    elif argv:
        paths = [Path(a) for a in argv]
    else:
        paths = staged_files()
    hits = scan(paths)
    for hit in hits:
        print(f"possible secret: {hit}", file=sys.stderr)
    if hits:
        print(
            f"{len(hits)} possible secret(s); refusing. Mark false positives with "
            f"'{ALLOW_MARKER}'.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
