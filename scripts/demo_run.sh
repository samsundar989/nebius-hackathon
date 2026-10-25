#!/usr/bin/env bash
# Replay for the video (docs/VIDEO_SCRIPT.md). Each step waits for Enter.
# Needs Docker and a .env with NEBIUS_API_KEY / NEBIUS_PROJECT_ID; costs about $0.02.
# On this machine heavy steps go through workerq; for recording, run it when the queue is idle.
set -euo pipefail
cd "$(dirname "$0")/.."
pause() { printf '\n\033[2m-- %s (Enter) --\033[0m\n' "$1"; read -r _; }

pause "1. the bug: csvsplit under AddressSanitizer"
# Git Bash would rewrite /tmp and /src into Windows paths; WSL ignores both settings.
HERE=$(pwd -W 2>/dev/null || pwd)
MSYS_NO_PATHCONV=1 docker run --rm -v "$HERE/examples/csvsplit:/src/csvsplit:ro" -w /tmp leakproof/cpp-sanitizers:e0 \
  bash -c 'cp -r /src/csvsplit /tmp/c && cd /tmp/c && make -s all CC=clang \
    CFLAGS="-fsanitize=address,undefined -g -O0" >/dev/null && ./csvsplit_fuzz poc.csv 2>&1 | head -12' || true

pause "2. leakproof fix: plan, 4 workers, the gate"
uv run leakproof fix --config examples/csvsplit/leakproof.toml --run-id demo_fix

pause "3. leakproof batch: 10 crash reports -> clusters -> one fix each -> every report re-checked"
uv run leakproof batch --config examples/csvsplit/leakproof.toml --findings examples/csvsplit/findings --run-id demo_batch

pause "4. evidence: bundles and the dashboard"
uv run python scripts/render_bundle.py p3_arvo27_r1 --all --out docs/bundles >/dev/null
sed -n '1,12p' docs/bundles/42530604.md
echo
echo "Dashboard: the Render static site, or: (cd site && python -m http.server 8765) -> http://127.0.0.1:8765"
