# Video script (≈ 2 min 50 s)

Screen + voice. Replay commands are in `scripts/demo_run.sh` (each step pauses for Enter).
Numbers are from `docs/NUMBERS.md`; re-check them the day of recording.

| time | on screen | say |
|---|---|---|
| 0:00–0:15 | Title card: "Leakproof — verified fixes, or nothing." | Memory bugs in C and C++ are found faster than anyone can fix them. AI can write patches — but most of them just make the crash go away. Leakproof only reports a fix when it can prove it. |
| 0:15–0:35 | `demo_run.sh` step 1: the csvsplit crash under AddressSanitizer | Here is a real heap overflow: a CSV splitter writes one byte past a buffer on quoted fields. The sanitizer catches it. |
| 0:35–1:10 | Step 2: `leakproof fix --config examples/csvsplit/leakproof.toml` running; the plan, four workers, the gate checks scrolling | Nemotron 3 Ultra on Nebius Token Factory finds the root cause and proposes fixes. Four Nemotron Lightning workers each patch a separate copy. Then the gate — its own process, network off — rebuilds, re-runs the crash, runs the project's tests, compares behaviour on a corpus, re-fuzzes with enlarged inputs, and checks for leaks. One cent; about two minutes. Verified. |
| 1:10–1:35 | Dashboard: the ARVO funnel (crash gone 18 → verified 15 of 27) | We ran it on 27 real OSS-Fuzz bugs in 13 open-source projects. 18 times the crash went away — that is where most tools stop. 15 survived the gate. |
| 1:35–1:55 | Bundle for jq 42530604: the stack buffer diff and the refuzz line "stack-buffer-overflow … from amplification" | This patch looked fine and passed every test. The gate made the input's digits sixty-four times longer and the fix overflowed the stack. The developer's real fix is clean on that same input. |
| 1:55–2:10 | Calibration table: 24 of 27 developer fixes accepted, 1 true reject | Is the gate just strict? We ran the developers' own fixes through it: it accepts 24 of 27 — and rejects one because that human fix actually leaks. |
| 2:10–2:25 | CUDA panel: two `silenced_only` candidates | Same on the GPU: two patches made NVIDIA's compute-sanitizer go quiet — one clamped the bound, one allocated an extra element — and both printed the wrong answer. Rejected. |
| 2:25–2:40 | Step 3: `leakproof batch --findings …` → "1 cluster, all 6 members clean" | Real projects have piles of reports. Batch mode groups them by root cause, fixes each group once, and re-checks every report against the fix. |
| 2:40–2:50 | README limitations + repo URL | Every number is regenerated from run records, failed runs included; the limitations are in the README. Leakproof: verified fixes, or nothing. |

Recording notes: run `scripts/demo_run.sh` once beforehand so images are pulled; keep the terminal at 110 columns; the dashboard is the Render static site (or `site/` served locally). Do not show `.env` or the Render environment page.
