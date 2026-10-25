#!/usr/bin/env python3
"""Silent video draft for Samuel to narrate over (review #6 order 2, v2 per review #7).

video/record.py  -> video/clips/<scene>.webm (Playwright, 1920x1080), video/captions.srt,
                    video/leakproof_draft.mp4 (concatenated, captions burned in)

Readable at 1080p and on a phone: terminal scenes use a 28 px font with at most 19 lines above a 150 px caption band; each
dashboard scene isolates one card, zooms it (CSS zoom) to fill the frame and pans slowly when it
is taller than the frame. Scenes follow docs/VIDEO_SCRIPT.md v2; terminal
scenes replay recorded runs (video/transcripts/, from video/build_transcripts.py). Needs
Playwright with Chromium and imageio-ffmpeg in the Windows venv; no model calls, no Docker.
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
W, H = 1920, 1080

# (scene, kind, target, seconds, caption) in script order. kind: card | term | dash.
SCENES = [
    ("00_title", "card", "title", 3, ""),
    (
        "01_jq_bundle",
        "term",
        "01_jq_bundle&d=700",
        12,
        "jq: the model's patch passed jq's own tests, and the original crash input no longer crashes.",
    ),
    (
        "02_refusal_card",
        "dash",
        "#refusal",
        15,
        "Leakproof doubled one number in that input: the patched jq overflows. Refused.",
    ),
    (
        "03_crash",
        "term",
        "03_crash&d=900",
        10,
        "A bug to fix live: a CSV splitter writes one byte past a buffer.",
    ),
    (
        "04_fix",
        "term",
        "04_fix&d=800",
        16,
        "Nemotron 3 Ultra plans; four Nemotron 3.5 Lightning workers patch; the gate verifies with the network off.",
    ),
    (
        "05_fix_diff",
        "term",
        "05_fix_diff&d=700",
        11,
        "The verified fix: one byte more for the terminator.",
    ),
    (
        "05_funnel",
        "dash",
        "funnel",
        14,
        "27 real OSS-Fuzz bugs: crash gone in 18, verified 15, correct 14.",
    ),
    (
        "06_calibration",
        "card",
        "calibration",
        10,
        "The gate accepts 24 of 27 of the developers' own fixes.",
    ),
    (
        "07_planner",
        "dash",
        "#planner",
        14,
        "Same Lightning workers, 10 real bugs: no planner 2, Super 4, Ultra 7 verified.",
    ),
    (
        "08_batch",
        "term",
        "07_batch&d=1000",
        11,
        "Batch mode: 10 crash reports, 1 root cause, fixed once, every report re-checked.",
    ),
    (
        "09_cuda",
        "dash",
        "#cuda",
        14,
        "On the GPU: two patches silenced compute-sanitizer and printed the wrong answer. Rejected.",
    ),
    (
        "10_mosquitto",
        "dash",
        "mosquitto",
        20,
        "Where it falls short: two mosquitto fixes passed every check yet were wrong. We report verified and correct.",
    ),
    ("11_end", "card", "end", 6, ""),
]

# Stage width per dashboard card: narrower stages zoom further, so short cards fill the frame.
STAGE = {"#refusal": 820, "funnel": 600, "#planner": 660, "#cuda": 560, "mosquitto": 880}

# Isolate one element at a stage width, zoom it to fill the frame above the 150 px caption band,
# and pan linearly only when it is far taller than the frame (zooming it to fit would be too small).
ISOLATE = """([sel, seconds, width]) => {
  const el = document.querySelector(sel).cloneNode(true);
  el.querySelectorAll('details').forEach(d => d.open = true);
  if (el.matches('details')) el.open = true;
  const stage = document.createElement('div');
  stage.style.cssText = `width:${width}px;margin:0 auto;padding:12px 0`;
  stage.appendChild(el);
  document.body.replaceChildren(stage);
  const byW = innerWidth * 0.95 / width, byH = (innerHeight - 170) / stage.offsetHeight;
  const pan = byH < byW * 0.6;
  stage.style.zoom = pan ? byW : Math.min(byW, byH);
  if (pan) stage.style.paddingBottom = `${170 / byW}px`;
  const extra = document.documentElement.scrollHeight - innerHeight;
  if (extra > 0) {
    const start = performance.now() + 2500, span = (seconds - 4.5) * 1000;
    const step = (t) => {
      const k = Math.min(Math.max((t - start) / span, 0), 1);
      window.scrollTo(0, extra * k);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}"""


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    # One server over the repo: /site/ for the dashboard, /video/ for terminal and cards.
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def play(page, base: str, kind: str, target: str, seconds: int) -> None:  # noqa: ANN001
    if kind == "card":
        # A static page gives Playwright no repaint to record, so a card is a screenshot (below).
        page.goto(f"{base}/video/card.html?type={target}")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(CLIPS / f"{target}.png"))
        return
    elif kind == "term":
        page.goto(f"{base}/video/terminal.html?t={target}")
    else:
        page.goto(f"{base}/site/index.html")
        page.wait_for_selector("#headline .stat")
        page.wait_for_selector("#cases button")
        sel = target
        if target == "funnel":
            sel = "#funnel"
            page.evaluate("document.querySelector('#funnel').closest('.panel').id = 'funnel-panel'")
            sel = "#funnel-panel"
        elif target == "mosquitto":
            page.evaluate(
                "[...document.querySelectorAll('#cases button')]"
                ".find(b => b.textContent.includes('42520955')).click()"
            )
            page.wait_for_selector("#case details")
            sel = "#case details"
        page.wait_for_timeout(300)
        page.evaluate(ISOLATE, [sel, seconds, STAGE[target]])
    page.wait_for_timeout(seconds * 1000)


def stamp(t: float) -> str:
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"


def main() -> int:
    CLIPS.mkdir(parents=True, exist_ok=True)
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scene, kind, target, seconds, _ in SCENES:
            # Full-HD viewport for every scene; dashboard cards are enlarged by CSS zoom (ISOLATE),
            # which renders text at full resolution.
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(CLIPS / "tmp"),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            play(page, base, kind, target, seconds)
            video = page.video
            ctx.close()
            shutil.move(video.path(), CLIPS / f"{scene}.webm")
            print("recorded", scene, flush=True)
        browser.close()
    srv.shutdown()
    shutil.rmtree(CLIPS / "tmp", ignore_errors=True)

    t, cues = 0.0, []
    for _, _, _, seconds, caption in SCENES:
        if caption:
            cues.append(
                f"{len(cues) + 1}\n{stamp(t + 0.3)} --> {stamp(t + seconds - 0.3)}\n{caption}\n"
            )
        t += seconds
    (VIDEO / "captions.srt").write_text("\n".join(cues), encoding="utf-8", newline="\n")

    # Each clip: skip the blank first frames, cut to length, draw its caption (drawtext, so no
    # libass is needed); then concatenate.
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    parts = []
    for scene, kind, target, seconds, caption in SCENES:
        out = CLIPS / f"{scene}.mp4"
        # Playwright records only when the page repaints, so a static stretch has few frames:
        # pad to the full scene length by repeating the last frame. Card scenes loop their
        # screenshot.
        src = (
            ["-loop", "1", "-i", str(CLIPS / f"{target}.png")]
            if kind == "card"
            else ["-ss", "0.8", "-i", str(CLIPS / f"{scene}.webm")]
        )
        vf = f"tpad=stop_mode=clone:stop_duration={seconds},fps=30,scale=1920:1080"
        if caption:
            text = caption.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
            text = text.replace(",", "\\,")
            vf += (
                f",drawtext=text='{text}':fontfile='C\\:/Windows/Fonts/segoeui.ttf':fontsize=40:"
                "fontcolor=white:box=1:boxcolor=black@0.72:boxborderw=18:x=(w-text_w)/2:y=h-110"
            )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                *src,
                "-t",
                str(seconds),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
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
