#!/usr/bin/env python3
"""Silent video draft for Samuel to narrate over (review #6 order 2).

video/record.py  -> video/clips/<scene>.webm (Playwright screen recordings, 1440x900),
                    video/captions.srt, video/leakproof_draft.mp4 (concatenated, captions burned in)

Scenes follow docs/VIDEO_SCRIPT.md v2: terminal replays of recorded runs (video/transcripts/,
built by video/build_transcripts.py) and the dashboard (site/, served locally). Needs Playwright
with Chromium and imageio-ffmpeg in the Windows venv; no model calls, no Docker.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "video"
CLIPS = VIDEO / "clips"
W, H = 1440, 900

# (scene, seconds, caption) in script order; captions condense the narration of VIDEO_SCRIPT v2.
SCENES = [
    (
        "01_jq_bundle",
        15,
        "jq: the model's patch passed jq's own tests, and the original crash input no longer crashes.",
    ),
    (
        "02_refusal_card",
        15,
        "Leakproof doubled one number in that input: the patched jq overflows. Refused.",
    ),
    ("03_crash", 15, "A bug to fix live: a CSV splitter writes one byte past a buffer."),
    (
        "04_fix",
        35,
        "Nemotron 3 Ultra plans; four Nemotron 3.5 Lightning workers patch; the gate verifies (network off).",
    ),
    (
        "05_funnel",
        30,
        "27 real OSS-Fuzz bugs: crash gone in 18, verified 15, correct 14. The gate accepts 24 of 27 developer fixes.",
    ),
    (
        "06_planner",
        15,
        "Same Lightning workers, 10 real bugs: no planner 2, Super 4, Ultra 7 verified.",
    ),
    (
        "07_batch",
        15,
        "Batch mode: 10 crash reports, 1 root cause, fixed once, every report re-checked.",
    ),
    (
        "08_cuda",
        15,
        "On the GPU: two patches silenced compute-sanitizer and printed the wrong answer. Rejected.",
    ),
    (
        "09_mosquitto",
        20,
        "Where it falls short: two mosquitto fixes passed every check yet were wrong. We report verified and correct.",
    ),
]


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    # One server over the repo: /site/ for the dashboard, /video/ for the terminal page.
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def smooth_scroll(page, selector: str, seconds: float) -> None:  # noqa: ANN001
    page.evaluate(
        "s => document.querySelector(s).scrollIntoView({behavior: 'smooth', block: 'start'})",
        selector,
    )
    page.wait_for_timeout(int(seconds * 1000))


def play(page, base: str, scene: str, seconds: int) -> None:  # noqa: ANN001
    ms = seconds * 1000
    if scene in ("01_jq_bundle", "03_crash", "04_fix", "07_batch"):
        page.goto(f"{base}/video/terminal.html?t={scene}")
        page.wait_for_timeout(ms)
        return
    page.goto(f"{base}/site/index.html")
    page.wait_for_selector("#headline .stat")
    page.wait_for_timeout(800)
    if scene == "02_refusal_card":
        smooth_scroll(page, "#refusal", 1.5)
        page.wait_for_timeout(ms - 2300)
    elif scene == "05_funnel":
        page.wait_for_timeout(9000)
        smooth_scroll(page, "#funnel", 9)
        smooth_scroll(page, "#calibration", 10.5)
    elif scene == "06_planner":
        smooth_scroll(page, "#planner", 1.5)
        page.wait_for_timeout(ms - 2300)
    elif scene == "08_cuda":
        smooth_scroll(page, "#cuda", 1.5)
        page.wait_for_timeout(ms - 2300)
    elif scene == "09_mosquitto":
        page.evaluate(
            "[...document.querySelectorAll('#cases button')].find(b => b.textContent.includes('42520955')).click()"
        )
        page.wait_for_timeout(600)
        smooth_scroll(page, "#case", 1.5)
        page.wait_for_timeout(4000)
        page.evaluate("document.querySelector('#case details').open = true")
        page.wait_for_timeout(800)
        page.evaluate(
            "document.querySelector('#case details').scrollIntoView({behavior: 'smooth'})"
        )
        page.wait_for_timeout(ms - 7700)


def stamp(t: float) -> str:
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"


def main() -> int:
    CLIPS.mkdir(parents=True, exist_ok=True)
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scene, seconds, _ in SCENES:
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(CLIPS / "tmp"),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            play(page, base, scene, seconds)
            video = page.video
            ctx.close()
            shutil.move(video.path(), CLIPS / f"{scene}.webm")
            print("recorded", scene, flush=True)
        browser.close()
    srv.shutdown()
    shutil.rmtree(CLIPS / "tmp", ignore_errors=True)

    # Captions: one cue per scene, timed by the scene lengths.
    t, cues = 0.0, []
    for i, (_, seconds, caption) in enumerate(SCENES, 1):
        cues.append(f"{i}\n{stamp(t + 0.3)} --> {stamp(t + seconds - 0.3)}\n{caption}\n")
        t += seconds
    (VIDEO / "captions.srt").write_text("\n".join(cues), encoding="utf-8", newline="\n")

    # Each clip trimmed to its scene length (recordings start with a short blank page), then
    # concatenated; captions are drawn per scene with drawtext so no libass is needed.
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    parts = []
    for scene, seconds, caption in SCENES:
        out = CLIPS / f"{scene}.mp4"
        text = (
            caption.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace(",", "\\,")
        )
        draw = (
            f"drawtext=text='{text}':fontfile='C\\:/Windows/Fonts/segoeui.ttf':fontsize=30:"
            "fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=14:x=(w-text_w)/2:y=h-90"
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-ss",
                "0.6",
                "-i",
                str(CLIPS / f"{scene}.webm"),
                "-t",
                str(seconds),
                "-vf",
                f"fps=30,{draw}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(out),
            ],
            check=True,
        )
        parts.append(out)
    listing = CLIPS / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(VIDEO / "leakproof_draft.mp4"),
        ],
        check=True,
    )
    print("wrote", VIDEO / "leakproof_draft.mp4", f"({t:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
