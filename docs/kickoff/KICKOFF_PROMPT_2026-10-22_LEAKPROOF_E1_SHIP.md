# KICKOFF PROMPT — Leakproof E1 "SHIP" (Oct 22 → submit Oct 29)

**To:** Claude Code (builder) · **From:** Samuel (operator) + Cowork strategist · **Date:** 2026-10-22 (Wed), 13:00 CDT
**Deadline:** Fri Oct 30, 2026, **12:00 PM CDT** (10:00 AM PDT). **Target: complete Devpost submission by Tue Oct 28 evening; final edits Wed Oct 29; Oct 30 morning = proofread only.**
**Repo:** `C:\Users\<user>\Documents\nebius-hackathon` = `/mnt/c/Users/<user>/Documents/nebius-hackathon` (WSL2). Run from WSL2. Read `CLAUDE.md` first; the E0 report (`docs/REPORT_E0.md`), `docs/DECISIONS.md` D-0001…D-0028, `docs/research/REVALIDATION_2026-10-22.md`, and `cases/arvo/shortlist_2026-10-22.json` are the inputs to this prompt. E0 passed; this prompt supersedes `KICKOFF_PROMPT_2026-10-14_LEAKPROOF_E0.md` §5's E1–E6 roadmap.

---

## 0. Situation and verdict

Re-validation on Oct 22 (three research passes): deadline unchanged; 25.8K participants; gallery unpublished. The memory-safety lane is still empty except **SegSense** (single-file C, Nano triage + Ultra rewrite, Tavily CWE refs, gate = "ASan silent + stdout unchanged on one input", hosted demo + video, 4-person team). The Python repair agents have converged on our architecture (planner + parallel workers in forked sandboxes + independent gate + receipts) — ~9 submission-complete Coding-track entries now, ~15 by Oct 30. The judges (Oct 20 live session) said: real problem for a real audience; the "aha" within ~30 s of the demo; one thing done well, each integration must serve the story; show **which model does what** on screen; **published limitations read as rigor**; packaging takes longer than you think.

**Decision: Leakproof ships, descoped.** What makes it stand out is not the loop (everyone has one) but: real multi-file C projects (ARVO) fixed and **verified** with a gate SegSense doesn't have (unpatched-trips proof, project tests, differential corpus, re-fuzz, safe-fix check), a named memory-safety benchmark table with honest failures (Juliet CWE slices + ~20 ARVO cases), a CUDA `compute-sanitizer` extension nobody has, and a Nemotron cost-per-verified-fix leaderboard.

## 1. Ship-mode rules (in addition to CLAUDE.md)

1. **No new research, no new frameworks, no refactors for their own sake.** Every hour goes to the deliverables in §3. If a step runs over its box, cut scope inside the step (fewer cases, simpler UI), never the step after it.
2. **Docker is the primary runner.** Sandboxes (Contree) only if approval arrives (`/whoami` → `permissions.spawn == true`): then add a thin REST backend (spawn with `"networking": {"enabled": false}`, poll `/v1/operations/{uuid}`, inspect) — ≤ 2 hours, behind a flag, featured in README/video if it works. Batch API is private beta: off the critical path; keep the 403 in FEEDBACK.md.
3. **Spend caps:** Token Factory total for the week ≤ **$25** (`LEAKPROOF_LEDGER_CAP_USD=25`); per-process default $3; any single action > $2 → HUMAN.md. Compute: Kaggle for CUDA (free); Nebius AI Cloud only as the Oct 27 stretch (≤ $2) and only if Samuel has answered Q0001.
4. **Disk policy (D-0027 stands):** one ARVO image on disk at a time, `docker rmi` after each case, all container work through workerq. Check free space on C: before every batch; stop and ask at < 10 GB.
5. **Daily report:** append a dated section to `docs/REPORT_SHIP.md` every day (done · numbers · spend · blockers · tomorrow). Commit after each deliverable; **push** at least once a day (`git push origin main`). Questions → `docs/HUMAN.md`; take the defaults in §6 when unanswered.
6. **Honesty is the product.** Every number in README/dashboard is produced by a script in the repo from `runs/` JSON; "silenced" is never reported as "verified"; failures stay in the tables with their reason.

## 2. Scope: keep / drop

| Keep (core) | Drop / defer |
|---|---|
| Docker Runner with checkpoint/branch (exists) | Contree SDK integration (REST-only if approved) |
| Ultra planner → N Lightning workers → gate → evidence bundle | Batch API, Nemotron 3.5 Super-VL, Nano Omni (removed from TF Aug 31) |
| Gate: unpatched-trips proof · patched clean · project tests · differential corpus · re-fuzz 60–120 s · safe-fix · diff-scope · LLM audit flag | Formal verification, TSan, Valgrind as a second oracle (mention as future work) |
| Juliet CWE-401/415/416 (existing 60 + a CWE-401 sample of ~100) | Full Juliet family runs |
| ARVO Tier-1 batch: ~20 cases from `cases/arvo/shortlist_2026-10-22.json` | Tier-2+, large images (lua/sudo/libdwarf/zstd/flac), leak mining beyond 3–5 commits (optional Day 4) |
| CUDA extension: 3 cases on Kaggle T4 via compute-sanitizer, Lightning/Ultra fix, re-verify | CUDA on the local 5090; CUDA perf; ncu |
| Model leaderboard on a fixed subset: Lightning-only vs Ultra+Lightning vs Super+Lightning (cost/verified fix, latency) | Fine-tuning, distillation, Nano-only runs beyond triage |
| Static dashboard (GitHub Pages) + Render free FastAPI "run one Juliet case" with rate limits + budget | Nebius Serverless Endpoint hosting; login-gated demo |
| PR-style evidence bundles on our own fork (patch + before/after logs + funnel + cost) | Real upstream PRs (all ARVO/Juliet bugs are already fixed upstream; a merged PR would need a *new* bug — opportunistic only) |
| README with numbers, architecture diagram, model→task legend, limitations, feedback; 3-min video; Devpost entry | Tavily grounding — optional Day 5, ≤ 3 h, only if on schedule (SegSense has it; judges called integrations that don't serve the story a negative) |

## 3. Phases, deliverables, exit criteria

### Phase 1 — Loop v1 · Wed Oct 22 (rest of day) → Thu Oct 23
- `leakproof/cases/arvo.py`: loader reading `~/.cache/leakproof/arvo/arvo.db` + the shortlist JSON → `Case{id, project, image, workdir, fuzz_target, crash_type, fix_commit, tests_cmd}`; `pull → run arvo (must trip) → rebuild with our flags (-O0, leak-sensitive) → run again (must trip) → snapshot baseline → … → docker rmi`. Verify the shortlist rows against the local arvo.db (fix the JSON if a row is wrong; note it in REPORT_SHIP).
- `leakproof/planner.py` (Nemotron 3 Ultra, thinking on, `max_completion_tokens` ≤ 16K): input = parsed Finding + the crashing frames' source windows (±80 lines per frame, up to 5 frames) + file list + build/test commands; output (structured, D-0012: enums/strings only) = `{root_cause, cwe, hypotheses:[{id, summary, files, strategy ∈ {add_free, remove_free, bounds_check, null_check, lifetime_fix, size_fix, init, other}, risk}]}` ranked, N ≤ 4.
- `leakproof/worker.py` (Nemotron 3.5 Lightning, thinking on, `max_completion_tokens` ≤ 6K, temperature per D-0013): one hypothesis → **search/replace edit blocks** (D-0026) over the files the planner named; apply with `patching.py`; re-prompt once on apply failure with the exact mismatch; produce a unified diff ourselves.
- `leakproof/branch.py`: fan out N workers from the baseline checkpoint (`save=True` images), semaphore ≤ 4, each in its own container; record op ids, elapsed, max_rss, cost.
- `leakproof/gate.py` v0 (separate process; workers never import it; read-only mount of tests/harness): (1) unpatched build trips under the same flags (re-run, D-0020); (2) patched build + PoC → clean (parsed report, D-0028 rule: tool error = inconclusive, never clean); (3) project tests pass under ASan (`tests_cmd`; libbpf: fuzzer over corpus); (4) diff-scope: only source files under `/src/<project>`, no tests/build scripts/flags, no `-fsanitize`/`ASAN_OPTIONS` edits, no deleted `free()` without an added one for the same object unless strategy=remove_free (double free). Verdict ∈ {verified, silenced_only, rejected:<reason>, build_failed, inconclusive}.
- Funnel JSON per case: `runs/<run>/<case>.json` = {finding, hypotheses, per-worker: edit/diff/build/gate results/cost/elapsed, verdict, winner}.
- Run: the 60 Juliet smoke cases end to end, then ARVO **mosquitto 42520955** and **jq 42530604**.
- **Exit (Thu night):** Juliet ≥ 50% verified with Lightning workers (if lower, fix prompts/edit format before moving on — this is the engine); both ARVO cases produce an honest funnel (verified or named rejection). REPORT_SHIP day 1–2.

### Phase 2 — Gate v1 + evals · Fri Oct 24 → Sat Oct 25
- Gate v1 adds: (5) **differential corpus**: run the harness on the project's fuzz seed corpus (`/src/<project>/**/corpus*`, `tests/` inputs, or 50 random inputs from the fuzzer's own generation) before/after — outputs/exit codes must match (crash input excluded); (6) **re-fuzz** the patched harness 60–120 s with libFuzzer (`-max_total_time`, seeded with corpus + PoC) → no new report; (7) **safe-fix**: full tests + corpus under ASan+LSan with the leak-sensitive config (D-0022) → no new leak/UAF/double-free; (8) **audit flag**: Nano (or Lightning, thinking off) reviews the diff with the PERFOPT six-check prompt → flags only, stored, never gates.
- Juliet CWE-401 sample: 100 cases (deterministic seed, excluding the smoke set) → fix rate, $/verified, latency. Reuse `juliet_select.py`.
- **ARVO Tier-1 batch**: all 26 Tier-1 cases, sequential, one image at a time via workerq, time-boxed 20 min/case; keep every failure with reason. Tier-2 only if time.
- **Model leaderboard** on a fixed subset (20 Juliet + the ARVO cases that reached the gate): Lightning-only (no planner) vs Ultra+Lightning vs Super+Lightning → verified rate, $/verified fix, p50 latency. Nano = triage/CWE classification accuracy vs ground truth on the same subset. `scripts/leaderboard.py` writes `runs/leaderboard.json`.
- Optional (Sat, ≤ 3 h): mine 3–5 "fix memory leak" commits from jq/libyaml/cJSON (`git log -i --grep=leak -- '*.c'`; parent = vul; test added by the fix = reproducer) as leak case studies; and the 30-min experiment: ARVO PoCs/corpora with `detect_leaks=1` to harvest incidental real leaks.
- **Exit (Sat night):** `runs/eval_summary.json` with per-CWE and per-model tables; ≥ 15 ARVO cases attempted; the three honest numbers the README will carry (Juliet verified %, ARVO verified %, $/verified fix).

### Phase 3 — Product surface + CUDA · Sun Oct 26
- `scripts/render_bundle.py`: per verified case, a PR-style markdown bundle (summary, root cause, diff, before/after sanitizer logs, test log, differential + re-fuzz summary, safe-fix result, funnel, cost, model legend) → `bundles/<case>.md`; push bundles to a `leakproof-bundles` branch or `docs/bundles/` (judges read GitHub).
- Dashboard: static site in `site/` (plain HTML + a little JS, no build step) reading `site/data/*.json` exported from `runs/` → run list → case page (finding, hypothesis tree, gate matrix per worker, funnel, cost, model legend) + leaderboard page + "limitations" page. Deploy with GitHub Pages from `site/` (or `docs/`). Dark/light both readable; the gate matrix is the hero visual.
- "Run one Juliet case" service: `service/` FastAPI image with clang + Juliet `testcasesupport`; whitelist of 20 Juliet IDs; one Lightning worker + gate v0 inline (no Docker needed); per-IP 3 runs/10 min, global 25 runs/day, `LEAKPROOF_BUDGET_USD=1.00`, pre-recorded result served when budget is exhausted (labelled). Deploy to Render free (Samuel creates the account; Q0008). Cold-start banner.
- CUDA extension on Kaggle T4 (`scripts/kaggle_cuda.py` exists): 3 cases — `oob_global.cu`, `leak_cudamalloc.cu`, add `race_shared.cu` — compute-sanitizer finding → Lightning fix (Ultra fallback) → re-verify on Kaggle → JSON into the dashboard with the "NVIDIA compute-sanitizer" badge. Model legend states which model fixed which.
- **Exit (Sun night):** dashboard live on GitHub Pages with real data; Render button works from a clean browser (or documented as pending Samuel's account); 3 CUDA cases recorded.

### Phase 4 — README + optional Nebius extras · Mon Oct 27
- README.md complete (sections already scaffolded): What it is (problem + audience: C/C++ and CUDA teams drowning in sanitizer/fuzzer findings; "83% of AI patches silence the crash, 45% are correct" — PATCHBENCH), How it works (diagram `docs/architecture.svg`), **How we use NVIDIA Nemotron** (Ultra = root cause/plan, Lightning = parallel workers, Nano = triage/audit flag, Super = alt planner; with measured $/verified fix), **How we use Nebius** (Token Factory: thinking control, structured outputs, parallel calls, metered; Sandboxes: status honestly; AI Cloud: if the stretch ran), Results (tables from `runs/eval_summary.json` + leaderboard), The evidence gate (8 checks + why "ASan silent + stdout unchanged" is not verification), Setup, Cost ledger (total incl. failed runs), Feedback (summary; full text in `docs/FEEDBACK.md`), Limitations (ARVO has no leaks; label≠crash; Juliet is synthetic; `-O1` hides bugs; Batch 403; Sandboxes beta; CUDA on Kaggle not Nebius; what the gate cannot prove).
- `docs/FEEDBACK.md` finalized per tool (measured, with exact errors and onboarding times).
- Stretch A (≤ 2 h, only if Q0001 answered yes): one Nebius Serverless L40S job running compute-sanitizer on the 3 CUDA cases (`--image nvidia/cuda:12.8.1-devel-ubuntu22.04 --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --disk-size 50Gi --timeout 1h --preemptible --follows-spot-price`); record job id, timings, $ → README + dashboard.
- Stretch B (≤ 2 h, only if Sandboxes approved): REST backend + offline gate run on 5 Juliet cases; lineage shown in the dashboard.
- Stretch C (≤ 3 h, only if everything above is green): Tavily grounding for the planner (CWE/CERT page + upstream API doc for the crashing function), citations in bundles.
- **Exit (Mon night):** README is submission-grade; all numbers regenerate from scripts.

### Phase 5 — Video + Devpost draft · Tue Oct 28
- `docs/VIDEO_SCRIPT.md` (Cowork provides the storyboard in §5; you fill in the exact case, timings, on-screen captions) and a `scripts/demo_run.sh` that replays the chosen ARVO case live in < 90 s (cached image, pre-pulled). Samuel records (screen + voice) and uploads to YouTube (public). Claude Code prepares: thumbnail (3:2), 3–5 gallery images (gate matrix, funnel, leaderboard, CUDA badge, architecture), the Devpost story in Markdown (`docs/DEVPOST.md`: name, tagline, story, built-with list, links, track, feedback text), and the pre-existing-project answer ("new project, started Oct 14").
- Samuel submits a complete rough entry on Devpost (editable until the deadline).
- **Exit (Tue night):** video public, Devpost entry submitted with all required fields.

### Phase 6 — Final numbers + freeze · Wed Oct 29
- Re-run the full eval if anything in the gate changed; refresh `site/data` and README tables; verify demo URL + Render button from a clean browser/incognito; check LICENSE visible on the GitHub repo page; spell-check README; final `docs/REPORT_SHIP.md`; push. Samuel makes the final Devpost edits. **Freeze by 21:00 CDT.** Oct 30 before 12:00 CDT: proofread via Devpost "View" only; never touch the video link after submission.

## 4. Design specifics (so no time is spent re-deciding)

- Model IDs: planner `nvidia/Nemotron-3-Ultra-550b-a55b`; workers `nvidia/Nemotron-3_5-Lightning`; triage/audit `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`; alt planner `nvidia/nemotron-3-super-120b-a12b`. Verify with `GET /v1/models` on Oct 28 (the recording day) and pin in `.env`.
- Thinking: on for planner and workers via `chat_template_kwargs.enable_thinking` (D-0011/D-0013) with hard `max_completion_tokens`; off for audit/triage. If a worker returns reasoning but no edit (E0 attempt 2), retry once with thinking off.
- Worker prompt contains: the Finding (kind, frames, alloc/free stacks), the planner's hypothesis + strategy, the exact file windows, the edit-block format with one example, and the rule "do not touch tests, build files, or sanitizer flags; do not add try/catch-style bypasses; prefer the smallest change." Workers never see the gate's corpus or re-fuzz settings.
- Edit format: `<<<<<<< SEARCH … ======= … >>>>>>> REPLACE` blocks per file; SEARCH must match exactly once (whitespace-insensitive fallback per D-0026); we generate the unified diff.
- Gate runs in a fresh container from the **baseline** image with the patch applied, `--network none`, read-only bind of `gate/` assets; verdict JSON schema in `leakproof/gate.py`.
- ARVO specifics: `cwd = case.workdir` (D-0024); flags per `docs/ARVO_NOTES.md` (`CFLAGS="-O0 -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"`); PoC at `/tmp/poc`; harness `/out/<fuzz_target>`; CWE from the **reproduced** report.
- Cost accounting: every bundle and the leaderboard show $ per case split by model; the README cost ledger = sum of `runs/cost_ledger.jsonl` incl. failed runs + Kaggle/Nebius compute.
- Dashboard data contract: `site/data/runs.json` (list), `site/data/cases/<id>.json`, `site/data/leaderboard.json`, `site/data/limitations.json`; generated by `scripts/export_site.py`.

## 5. Video storyboard (3:00 max; Samuel narrates)

0:00–0:25 Problem: a real ASan trace scrolls; "Sanitizers and fuzzers find thousands of memory bugs; AI patches silence 83% of them but only 45% are right. Leakproof ships a fix only when the evidence survives a gate the model can't see."
0:25–1:30 Live: `leakproof fix n132/arvo:<case>` on a real OSS project (mosquitto or jq) — crash reproduces; Ultra's hypotheses appear; four Lightning workers branch; the gate matrix fills: two candidates silence the crash but fail re-fuzz/differential (named reasons), one survives; bundle opens with before/after logs. Caption legend: Ultra = plan · Lightning = workers · Nano = triage.
1:30–2:05 Numbers: Juliet and ARVO tables; the raw-vs-verified funnel; cost per verified fix; model leaderboard.
2:05–2:35 CUDA: compute-sanitizer finding on a kernel → fixed → re-verified (Kaggle T4; Nebius Serverless if the stretch ran).
2:35–2:55 Limitations slide (ARVO has no leaks; -O1 hides bugs; Sandboxes beta; what the gate can't prove) + "built on Nebius Token Factory with Nemotron 3 Ultra, 3.5 Lightning and Nano" said aloud.
2:55–3:00 Repo + dashboard URLs.

## 6. HUMAN.md defaults in force until Samuel answers
- Q0001 (AI Cloud): assume **not funded** → skip Stretch A. Q0002/Q0005 (Sandboxes): assume **not approved** → Docker. Q0003 (disk): assume **not compacted** → one image at a time, stop at < 10 GB free. Q0004 (leaks): option (a). Q0006 (local CUDA): leave the machine alone; Kaggle. New: **Q0007** — confirm Kaggle GPU quota is free for ~2 h this week (default: assume yes, ≤ 1 h of T4). **Q0008** — Render account for the demo button (default: build the service, deploy when he confirms; dashboard on GitHub Pages needs no new account). **Q0009** — who narrates the video (default: Samuel, screen + voice, Oct 28).

## 7. Gate SHIP (what "done" means on Oct 29)
- [ ] Public repo, MIT visible, README with regenerated numbers, architecture diagram, model legend, limitations, feedback.
- [ ] `runs/eval_summary.json` + `runs/leaderboard.json` + bundles for every verified case; failures listed with reasons.
- [ ] Dashboard on GitHub Pages; Render button live or documented; CUDA cases recorded.
- [ ] Video < 3 min public on YouTube, Nebius/Nemotron named aloud; Devpost entry complete (track: Coding & Agentic Engineering; feedback field filled; built-with tags).
- [ ] Total TF spend ≤ $25 and visible; everything pushed.
