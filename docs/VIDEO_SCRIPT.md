# Video script v2 (≈ 2 min 55 s)

Screen + voice. Replay commands are in `scripts/demo_run.sh` (each step pauses for Enter; the steps follow this script's order).
Numbers are from `docs/NUMBERS.md` and the dashboard (both generated from the same run records); re-check them the day of recording.

| time | on screen | say |
|---|---|---|
| 0:00–0:30 | `demo_run.sh` step 1: jq bundle, first lines "Not fixed … refuzz: heap-buffer-overflow at decToString … from amplification:digits_x2"; then the dashboard's refusal card | This patch for a real jq bug passed jq's own test suite, and the original crash input no longer crashes. Most repair tools would ship it. Leakproof doubled one number in that input, and the patched jq overflowed a heap buffer. The unpatched program and the developer's real fix are both clean on that input, so Leakproof refused the patch. Leakproof: verified fixes, or nothing. |
| 0:30–0:45 | Step 2: the csvsplit crash under AddressSanitizer | Here's a bug of our own to fix live: a CSV splitter writes one byte past a buffer on quoted fields. |
| 0:45–1:20 | Step 3: `leakproof fix --config examples/csvsplit/leakproof.toml`: the plan, four workers, the gate checks scrolling | Nemotron 3 Ultra on Nebius Token Factory finds the root cause and plans the fixes. Four Nemotron 3.5 Lightning workers each patch their own copy. Then the gate, in its own process with the network off, rebuilds, re-runs the crash, runs the project's tests, compares behaviour on a corpus, re-fuzzes with enlarged inputs and checks for leaks. About two minutes and one cent. Verified. |
| 1:20–1:50 | Dashboard first screen: 15/27 verified, 14/27 verified and correct; the funnel; the calibration line | On 27 real OSS-Fuzz bugs from 13 open-source projects, the crash went away 18 times, which is where most tools stop. 15 survived the gate. Then we checked every verified fix against the developer's own fix: 14 are correct. And the gate is not just strict: it accepts 24 of 27 of the developers' own fixes. |
| 1:50–2:05 | Dashboard planner card: 2/10 → 4/10 → 7/10 | Which model does what? On real bugs, Ultra's plan takes the same Lightning workers from 2 to 7 verified fixes out of 10, and each fix costs less, because failed attempts cost money too. |
| 2:05–2:20 | Step 4: `leakproof batch --findings …` → "1 cluster, all 6 members clean" | Real projects have piles of crash reports. Batch mode groups them by root cause, fixes each group once, and re-checks every report against the fix. |
| 2:20–2:35 | Dashboard CUDA panel: two `silenced_only` candidates | The same on the GPU: two patches made NVIDIA's compute-sanitizer go quiet, and both printed the wrong answer. Rejected. |
| 2:35–2:55 | README "How a gate lies", mosquitto item; then the repo URL | Where it falls short: a fuzz harness only sees what it prints. Two mosquitto patches passed every check yet pointed the config at the wrong listener. Our review caught them, and we report "verified and correct" next to "verified". The gate runs on Nebius Sandboxes with networking off; every number is generated from run records, failed runs included. Leakproof: verified fixes, or nothing. |

Accuracy notes for the narration (do not drop when shortening):
- The jq refusal is P3 run 1, case 42530604 (worker H2·w1); the verified one-line fix (`digits + 20`) is from run 2.
- Say "on Nebius Sandboxes" only about the gate in general: the Juliet runs used Sandboxes; ARVO images do not import there yet, so ARVO ran on local Docker (README).
- The planner comparison is one repeat on 10 cases (2/4/7 verified; verified and correct 2/2/5).

Recording notes: run `scripts/demo_run.sh` once beforehand so images are pulled; keep the terminal at 110 columns; the dashboard is the Render static site (or `site/` served locally: `cd site && python -m http.server 8765`). Do not show `.env` or the Render environment page.
