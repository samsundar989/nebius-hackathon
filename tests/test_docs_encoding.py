"""Tracked docs must be valid UTF-8 with no U+FFFD (Windows cp1252 writes show up as that on GitHub)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tracked_docs() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "README.md", "docs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [ROOT / p for p in out.splitlines() if p.endswith(".md")]


def test_docs_are_clean_utf8() -> None:
    docs = _tracked_docs()
    assert docs
    bad: list[str] = []
    for path in docs:
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            bad.append(f"{path.relative_to(ROOT)}: invalid UTF-8 at byte {e.start}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "�" in line:
                bad.append(f"{path.relative_to(ROOT)}:{lineno}: U+FFFD")
    assert not bad, "\n".join(bad)
