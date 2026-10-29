#!/usr/bin/env python3
"""Silent video draft for Samuel to narrate over (review #6 order 2, v2 per review #7).

video/record.py  -> video/clips/<scene>.webm (Playwright, 1920x1080), video/captions.srt,
                    video/leakproof_draft.mp4 (concatenated, captions burned in)

Readable at 1080p and on a phone: terminal scenes use a 28 px font with at most 19 lines above a 150 px caption band; each
dashboard scene isolates one card, zooms it (CSS zoom) to fill the frame and pans slowly when it
is taller than the frame. Scenes follow docs/VIDEO_SCRIPT.md v4 (video v6); terminal
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

# (scene, kind, target, seconds, caption) in script order (v6, review #22: recorded from the new
# dashboard). kind: card | term | dash | demo.
SCENES = [
    ("00_title", "card", "title", 3, ""),
    (
        "01_hero",
        "dash",
        "hero",
        8,
        "Leakproof fixes memory bugs in C, C++ and CUDA, then tries to break every patch.",
    ),
    (
        "02_head_to_head",
        "dash",
        ".verdicts",
        18,
        "78 patches made a real crash go away. A crash-is-gone check ships 21 bad ones; Leakproof 4.",
    ),
    (
        "03_recheck",
        "demo",
        "recheck",
        14,
        "Anyone can re-run the gate on a stored patch: no AI, $0, on our server (recorded response).",
    ),
    (
        "04_how",
        "dash",
        "#how",
        16,
        "Nebius Token Factory: Nemotron Ultra plans, four Lightning workers patch, Super attacks.",
    ),
    (
        "05_fix",
        "term",
        "04_fix&d=800",
        14,
        "A recorded run on a CSV splitter: the gate verifies the patch with the network off.",
    ),
    (
        "06_refusal",
        "dash",
        "#refusal-sec",
        15,
        "jq: a patch passed jq's own tests. Leakproof doubled one number in the input; it overflowed. Refused.",
    ),
    (
        "07_still_open",
        "dash",
        "#real",
        13,
        "New bugs, reported after the models' training: our 2-line gpac fix matches the fix gpac shipped on Oct 29.",
    ),
    (
        "08_explorer",
        "dash",
        "explorer",
        14,
        "Every run, every check, with its evidence.",
    ),
    (
        "09_limits",
        "dash",
        "#limitations",
        9,
        "Verified means safe on every input we tried, not proven correct. A person decides what is sent.",
    ),
    ("10_end", "card", "end", 6, ""),
]

# Stage width per dashboard target: narrower stages zoom further, so short cards fill the frame.
STAGE = {
    "hero": 900,
    ".verdicts": 1000,
    "recheck": 900,
    "#how": 1000,
    "#refusal-sec": 900,
    "#real": 1100,
    "explorer": 1000,
    "#limitations": 900,
}
# The re-check scene replays a real response captured from the Render demo service
# (video/reverify_render.json), so the recording does not wait on a sleeping free instance.
REVERIFY = VIDEO / "reverify_render.json"

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
    elif kind == "demo":
        svc = "https://leakproof-demo.onrender.com"
        page.route("**/site/config.json", lambda r: r.fulfill(json={"service_url": svc}))
        page.route(f"{svc}/healthz", lambda r: r.fulfill(json={"ok": True}))
        page.route(
            f"{svc}/reverify",
            lambda r: r.fulfill(body=REVERIFY.read_text(), content_type="application/json"),
        )
        page.goto(f"{base}/site/index.html")
        page.wait_for_selector("#waffle .tile")
        page.click("#reverify")
        page.wait_for_selector("#demo-out .case")
        # The buttons, the note and the result, without the waffle below them.
        page.evaluate(
            "() => { const h = document.querySelector('.hero'); h.id = 'recheck';"
            " h.querySelectorAll('.verdicts, #proof, h1, .sub').forEach(e => e.remove()); }"
        )
        page.evaluate(ISOLATE, ["#recheck", seconds, STAGE[target]])
    else:
        page.goto(f"{base}/site/index.html")
        page.wait_for_selector("#waffle .tile")
        page.wait_for_selector("#cases button")
        sel = target
        if target == "hero":
            page.evaluate(
                "() => { const h = document.querySelector('.hero').cloneNode(true); h.id = 'hero-only';"
                " h.querySelectorAll('.verdicts, #proof, .actions, #demo-note, #demo-out')"
                ".forEach(e => e.remove()); document.querySelector('main').append(h); }"
            )
            sel = "#hero-only"
        elif target == "#real":
            page.wait_for_selector("#rw tbody tr")
            # The scene shows the attempted issues; the already-fixed ones are in REAL_WORLD.md.
            page.evaluate(
                "document.querySelectorAll('#rw tbody tr').forEach("
                "r => /already fixed|dropped/i.test(r.textContent) && r.remove())"
            )
        elif target == "explorer":
            page.evaluate(
                "[...document.querySelectorAll('#cases button')]"
                ".find(b => b.textContent.includes('42531297')).click()"
            )
            page.wait_for_timeout(400)
            sel = "#runs"
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
