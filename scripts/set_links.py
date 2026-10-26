#!/usr/bin/env python3
"""Put the real links in, everywhere at once (review #11 order 3d).

scripts/set_links.py --dashboard URL --video URL [--devpost URL] [--repo URL] [--rebuild-video]

Replaces the placeholders in README.md, docs/DEVPOST.md and the video end card. Each link is
optional; a placeholder stays until its link is given. --rebuild-video re-records the silent cut
(video/record.py) so the end card shows the dashboard. Prints every change; --dry-run writes
nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/samsundar989/nebius-hackathon"


def host(url: str) -> str:
    u = urlparse(url)
    return (u.netloc + u.path).rstrip("/")


def edits(a: argparse.Namespace) -> dict[str, list[tuple[str, str]]]:
    readme, devpost, card = [], [], []
    if a.dashboard:
        readme.append(
            ("**Live dashboard** (link when deployed)", f"**[Live dashboard]({a.dashboard})**")
        )
        devpost += [
            ("live dashboard [Render static site URL]", f"live dashboard {a.dashboard}"),
            ("- Dashboard: [dashboard URL]", f"- Dashboard: {a.dashboard}"),
        ]
        card.append(
            (
                '<div class="links">github.com/samsundar989/nebius-hackathon</div>',
                '<div class="links">github.com/samsundar989/nebius-hackathon<br>'
                f"{host(a.dashboard)}</div>",
            )
        )
    if a.video:
        readme.append(
            ("**3-minute video** (link when recorded)", f"**[3-minute video]({a.video})**")
        )
        devpost += [
            ("video [YouTube URL]", f"video {a.video}"),
            ("- Video: [YouTube URL]", f"- Video: {a.video}"),
        ]
    if a.devpost:
        readme.append(("**Devpost** (link when submitted)", f"**[Devpost]({a.devpost})**"))
    devpost += [
        ("repository [GitHub URL]", f"repository {a.repo}"),
        ("- Repository: [GitHub URL]", f"- Repository: {a.repo}"),
    ]
    return {"README.md": readme, "docs/DEVPOST.md": devpost, "video/card.html": card}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboard")
    ap.add_argument("--video")
    ap.add_argument("--devpost")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--rebuild-video", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    changed = 0
    for rel, pairs in edits(a).items():
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        for old, new in pairs:
            if old in text:
                text = text.replace(old, new)
                changed += 1
                print(f"{rel}: {old[:50]!r} -> {new[:70]!r}")
            elif new not in text:
                print(f"{rel}: placeholder not found: {old[:60]!r}", file=sys.stderr)
        if not a.dry_run:
            p.write_text(text, encoding="utf-8", newline="\n")
    print(f"{changed} replacement(s){' (dry run)' if a.dry_run else ''}")
    if a.rebuild_video and not a.dry_run:
        subprocess.run([sys.executable, str(ROOT / "video" / "record.py")], check=True)
        # A narrated final cut made before this keeps the old end card: re-mix it from the
        # narration video/mux.sh recorded.
        saved = ROOT / "video" / ".narration_path"
        if saved.exists():
            voice = saved.read_text(encoding="utf-8").strip()
            subprocess.run(["bash", str(ROOT / "video" / "mux.sh"), voice], check=True)
            print(f"re-mixed video/leakproof_final.mp4 with {voice}")
        else:
            print("no narration recorded yet: run video/mux.sh after recording")
    return 0


if __name__ == "__main__":
    sys.exit(main())
