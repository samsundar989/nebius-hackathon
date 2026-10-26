#!/usr/bin/env bash
# Wednesday's freeze check (review #14 order 5): one PASS/FAIL line per item, exit 1 on any FAIL.
#
#   bash scripts/freeze_check.sh
#   (on Windows, with the Windows venv: UV_PROJECT_ENVIRONMENT=.venv-win bash scripts/freeze_check.sh)
#
# Checks: numbers regenerate with no drift; unit tests, ruff and the secret scan; every relative
# link resolves; no link placeholders left; the dashboard's live-run mode is configured or the
# recorded mode is stated; the final video exists and is at most 2:59; README/DEVPOST numbers
# match site/data/numbers.json; the working tree is clean and pushed. No model calls.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# 1. Numbers: regenerate, then nothing may change.
if uv run python scripts/readme_numbers.py > /dev/null 2>&1 \
  && git diff --quiet -- docs/NUMBERS.md site/data/numbers.json; then
  pass "numbers regenerate with no drift"
else
  fail "numbers drift: $(git diff --stat -- docs/NUMBERS.md site/data/numbers.json | tail -1)"
fi

# 2. Tests, lint, secrets.
if uv run pytest -q -m "not network and not docker and not contree" > /tmp/lp_freeze_tests.log 2>&1; then
  pass "unit tests ($(tail -1 /tmp/lp_freeze_tests.log))"
else
  fail "unit tests: $(tail -1 /tmp/lp_freeze_tests.log)"
fi
if uv run ruff check -q . && uv run ruff format --check -q .; then pass "ruff"; else fail "ruff"; fi
if python3 scripts/check_secrets.py --all > /dev/null 2>&1 || python scripts/check_secrets.py --all > /dev/null 2>&1; then
  pass "secret scan"
else
  fail "secret scan"
fi

# 3-7. Links, placeholders, live-run mode, video, numbers in the prose.
uv run python - > /tmp/lp_freeze_py.log 2>&1 <<'PY'
import glob
import json
import os
import re
import subprocess

def say(ok, text):
    print(("PASS  " if ok else "FAIL  ") + text)
    return ok

docs = ["README.md", "docs/DEVPOST.md", "docs/WALKTHROUGH.md", "docs/SUBMISSION_CHECKLIST.md",
        "cases/open_bugs/REVIEW.md", "cases/open_bugs/INIT_EVAL.md",
        *glob.glob("docs/bundles/*.md"), *glob.glob("examples/**/README.md", recursive=True),
        *glob.glob("cases/open_bugs/**/SUBMISSION.md", recursive=True)]
docs = [d for d in docs if os.path.exists(d) and subprocess.run(
    ["git", "ls-files", "--error-unmatch", d], capture_output=True).returncode == 0]
broken = []
for d in docs:
    for m in re.finditer(r"\]\(([^)\s]+)\)", open(d, encoding="utf-8").read()):
        u = m.group(1).split("#")[0]
        if u and not u.startswith(("http", "mailto")) and not os.path.exists(
            os.path.normpath(os.path.join(os.path.dirname(d), u))
        ):
            broken.append(f"{d}: {m.group(1)}")
ok = say(not broken, f"relative links resolve ({len(docs)} files)" + (f": {broken[:5]}" if broken else ""))

marks = ["(link when", "[GitHub URL]", "[YouTube URL]", "[dashboard URL]", "[Render static site URL]"]
left = [f"{f}: {m}" for f in ("README.md", "docs/DEVPOST.md") for m in marks
        if m in open(f, encoding="utf-8").read()]
card = open("video/card.html", encoding="utf-8").read()
if "<br>" not in card.split('class="links"')[-1].split("</div>")[0]:
    left.append("video/card.html: no dashboard link on the end card")
ok &= say(not left, "no link placeholders left" + (f" ({len(left)}: {left[:4]})" if left else ""))

cfg = json.load(open("site/config.json")) if os.path.exists("site/config.json") else {}
stated = "recorded run" in open("site/index.html", encoding="utf-8").read()
ok &= say(bool(cfg.get("service_url")) or stated,
          "live runs: " + (f"service_url {cfg['service_url']}" if cfg.get("service_url")
                           else "off; the dashboard states recorded mode"))

final = "video/leakproof_final.mp4"
if os.path.exists(final):
    import imageio_ffmpeg
    err = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", final],
                         capture_output=True, text=True).stderr
    h, m_, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    secs = int(h) * 3600 + int(m_) * 60 + float(s)
    ok &= say(secs <= 179, f"final video {final}: {secs:.0f} s (limit 179)")
    # The final cut must be newer than everything baked into it: the end card, the silent cut
    # and the narration (set_links.py --rebuild-video re-mixes after the links change).
    inputs = ["video/card.html", "video/leakproof_draft.mp4"]
    if os.path.exists("video/.narration_path"):
        inputs.append(open("video/.narration_path", encoding="utf-8").read().strip())
    stale = [f for f in inputs if os.path.exists(f) and os.path.getmtime(f) > os.path.getmtime(final)]
    ok &= say(not stale, "final video newer than its inputs" + (f": older than {stale}" if stale else ""))
else:
    ok &= say(False, f"final video missing ({final}: run video/mux.sh with the narration)")

n = json.load(open("site/data/numbers.json"))
r1, ob, cal = n["arvo"]["p3_arvo27_r1"], n["open_bugs"]["total"], json.load(open("site/data/calibration.json"))
acc = cal["adjudicated"]["classes"]["accepted"]
want = {
    "README.md": [f"{r1['verified']}/{r1['cases']}", f"{acc}/{cal['adjudicated']['judged']}",
                  f"On {ob['triaged']} open GitHub issues", f"verified a fix for {ob['verified']}"],
    "docs/DEVPOST.md": [f"{r1['verified']} of {r1['cases']} real OSS-Fuzz bugs", f"{r1['strict']} of them correct",
                        f"{acc} of {cal['adjudicated']['judged']}", f"{ob['triaged']} open GitHub issues",
                        f"{ob['reproduce_no_pr']} still reproduce", f"{ob['verified']} verified"],
}
miss = [f"{f}: '{w}'" for f, ws in want.items() for w in ws if w not in open(f, encoding="utf-8").read()]
ok &= say(not miss, "README/DEVPOST numbers match numbers.json" + (f": missing {miss}" if miss else ""))
raise SystemExit(0 if ok else 1)
PY
cat /tmp/lp_freeze_py.log
fails=$((fails + $(grep -c '^FAIL' /tmp/lp_freeze_py.log)))
grep -q '^PASS\|^FAIL' /tmp/lp_freeze_py.log || fails=$((fails + 1))

# 8. Clean and pushed.
git fetch -q origin 2>/dev/null
if [ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$(git rev-parse @{u} 2>/dev/null)" ]; then
  pass "working tree clean and pushed"
else
  fail "working tree: $(git status --porcelain | wc -l) change(s); ahead/behind: $(git rev-list --left-right --count HEAD...@{u} 2>/dev/null)"
fi

echo
if [ "$fails" -eq 0 ]; then echo "FREEZE CHECK: all PASS"; else echo "FREEZE CHECK: $fails FAIL"; fi
[ "$fails" -eq 0 ]
