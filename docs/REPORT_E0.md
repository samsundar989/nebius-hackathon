# REPORT — Experiment 0 (Foundation)

Date: 2026-10-14. Scope: `docs/kickoff/KICKOFF_PROMPT_2026-10-14_LEAKPROOF_E0.md`. Defaults in force (from Samuel): step 3.7's AI Cloud part skipped; Sandboxes expected unapproved.

**Total E0 model spend: $0.0116** (67 ledger rows in `runs/cost_ledger.jsonl`; cap $5). AI Cloud spend: $0 (skipped).

## Gate E0 status

| Criterion | Status |
|---|---|
| Token Factory: Ultra + Lightning + Nano work; thinking toggle known; json_schema behaviour known; ledger + budget guard proven | **Pass.** All four Nemotron models work (Super too). Toggle = `chat_template_kwargs.enable_thinking`. json_schema is enforced but numeric fields run away (Lightning 4/4). Budget stop forced in `tests/test_llm_client.py::test_budget_guard_forces_stop`. |
| LocalDockerRunner passes contract tests; ContreeRunner passes or is blocked only by approval | **Pass.** Docker 9/9. Contree 9/9 skipped: "200 on /whoami but spawn permission is false". |
| 60 Juliet cases build, reproduce, parse (≥ 95%); good-only variants clean | **Pass: 58/60 = 96.7%** reproduce + parse; 60/60 build; 60/60 good-only free of the target flaw (45/60 strictly clean — the 15 CWE-416 good functions leak by design). |
| 3 ARVO cases reproduce and parse; ARVO_NOTES written | **Pass.** 3/3 reproduce, rebuild and reproduce, and reproduce under our `-O0` flags. |
| One Serverless L40S job with compute-sanitizer output | **Skipped by instruction** (QUESTION 0001 unanswered). |
| Total E0 spend ≤ $5, visible in ledger | **Pass** ($0.0116). |

Local CUDA check (3.7, second half): **pending.** It is queued as workerq #2802 and waiting for GPU memory behind another project's high-priority jobs. Nothing is measured yet.

## 3.2 Token Factory (details in FEEDBACK.md)

| | Ultra | Lightning | Nano | Super |
|---|---|---|---|---|
| hello latency | 1.5 s | 3.0 s (846 reasoning tokens!) | 1.5 s | 1.5 s |
| reasoning field | `reasoning_content` | `reasoning_content` | `reasoning` (tokens reported as 0) | `reasoning_content` |
| thinking-off, two-step probability Q | right via ctk; wrong via `reasoning_effort=none` | wrong both ways | wrong (ctk); empty output (`reasoning_effort=none`) | writes CoT into content |
| effort low/high honoured | no | no | n/a | yes (28 vs 92 tokens) |
| json_schema | enforced; numeric runaway 1/5 | enforced; numeric runaway 4/4 | clean | clean |
| parallel tool calls | yes | yes | yes | yes |

- Rate-limit headers: `x-ratelimit-limit-requests: 600`, `x-ratelimit-limit-tokens: 400000`, plus `dynamic-scale`/`dynamic-period` headers. 20 concurrent Lightning calls: 20/20 OK, no 429, wall 3.1 s, p50 1.7 s.
- Batch API: `HTTP 403 {'detail': 'Creating new batch job is temporarily unavailable'}`. Retry in E1/E4.

## 3.3 Runner

| Measurement | Value |
|---|---|
| `cpp-sanitizers` image (ubuntu 24.04, clang-18, gcc-13, valgrind, heaptrack, AFL++) | 1.85 GB; cold build ~100 s |
| `cuda-dev` image (`nvidia/cuda:12.6.3-devel-ubuntu22.04` + cmake) | 11.5 GB on disk; 274 s (232 s pulling) |
| disposable `run("true")` | median 1.55 s (1.35–2.06, n=5) |
| `run(save=True)` (docker commit) | 5.3–8.0 s |
| 4 parallel branches from one checkpoint | 3.55 s wall |
| LSan inside Docker | works **without** `SYS_PTRACE` |
| Contree | not approved; SDK 0.3.6 has no networking switch (`UnsupportedOption`) |

## 3.4 / 3.5 Findings + Juliet smoke set

Parsers: ASan/LSan/UBSan/MSan, Valgrind, compute-sanitizer (format-tolerant stub; real fixtures pending the CUDA job). 100% of captured Juliet and ARVO reports parse to the expected kind (`tests/test_juliet_reports.py`, `tests/test_arvo_reports.py`).

Juliet 1.3 (SARD 112, sha256 `ada9d7e1…f38eb`): 60 cases chosen deterministically (seed 112) for diversity — 30 CWE-401 (15 C / 15 C++), 15 CWE-415, 15 CWE-416, every case a distinct functional + flow variant. Excluded up front: flow variant 12 (random branch) and `malloc_realloc_*` (leaks only if realloc fails). The whole set runs in ~30 s (3 parallel containers, 1.4 s mean per case, bad + good builds).

**Detection depends heavily on build flags** — the most useful E0 result for the gate:

| Configuration | CWE-401 | CWE-415 | CWE-416 | Total |
|---|---|---|---|---|
| kickoff: `-O1` | 27/30 | 13/15 | 14/15 | 54/60 (90%) |
| OSS-Fuzz style: `-O1 -fno-omit-frame-pointer`, default LSan | **21/30** | 13/15 | 14/15 | 48/60 (80%) |
| **adopted: `-O0` + `LSAN_OPTIONS=use_stacks=0`** | 29/30 | 15/15 | 14/15 | **58/60 (96.7%)** |

Root causes, each confirmed by hand:
- `-O1` deletes `malloc/free/free` sequences, so 2 double frees vanish.
- With `-O1 -fno-omit-frame-pointer`, stale pointer copies keep leaked blocks "reachable" for LSan's conservative scan, so 9 leaks go unreported.
- Remaining misses are by design: a leak still referenced from a global at exit (`_68`), and a use-after-free read that happens only inside `wprintf` in uninstrumented libc (`wchar_t_62`). Both stay in the set, marked `reproducible: false` with the reason; nothing was re-selected on outcome.

Implication (D-0020, D-0022): a "sanitizer-clean" verdict is only meaningful together with proof that the *unpatched* build trips under the same configuration, and leak checks must use the leak-sensitive configuration. Otherwise silencing looks like fixing.

## 3.6 ARVO (details in ARVO_NOTES.md)

md4c 42493685 (heap overflow), lua 42508415 (labelled UAF, **reproduces as heap overflow**), sudo 42492467 (double free). Pull ~55 s cold, 5.3–5.6 GB on disk each, `arvo` 0.33 s, `arvo compile` 19–54 s at 2 CPUs. **ARVO contains zero leak cases** and runs with `detect_leaks=0` (QUESTION 0004). `build.sh` is relative to the image WORKDIR, which Contree drops, so each case stores `workdir`.

## 3.8 Stretch: hello fix (CWE401 `char_malloc_05`, Nemotron 3.5 Lightning)

| Attempt | Thinking | Tokens out | $ | Strict `patch` | Tolerant apply | Verified (bad LSan-clean + good clean) |
|---|---|---|---|---|---|---|
| 1 | off | 275 | 0.00012 | no (misquoted context) | yes | **yes** |
| 2 | on | 8,192 (all reasoning, no diff) | 0.0020 | — | — | no |
| 3 | off | 241 | 0.00011 | no | yes | no — deleted an `if` line, leak remains |
| 4 | off | 730 | 0.00023 | no | no (invented edits to `main`) | no |
| 5 | off | 852 | 0.00026 | no | no (duplicated, malformed hunks) | no |

Raw-vs-verified in miniature: **1/4 thinking-off attempts verified**, 0/4 accepted by strict `patch`. The good-path reference code was stripped from the prompt (Juliet ships the fix next to the bug), so this is a plumbing test, not a capability score.

## What doesn't work / open issues

1. AI Cloud Serverless job — skipped (QUESTION 0001).
2. Sandboxes — not approved; SDK 0.3.6 can't disable networking.
3. Batch API — 403 "temporarily unavailable".
4. Local CUDA / compute-sanitizer run — queued (workerq #2802), not yet run. Risk to check: CUDA 12.6's compute-sanitizer may not support the 5090 (sm_120); if so, record the error and use a 12.8+ image for local runs. L40S (sm_89) is unaffected.
5. **The machine crashed mid-session.** Contributing factors I created: Docker's data disk on C: grew 15.6 → 45.3 GB (C: at 100%), and containers ran directly instead of through workerq. Fixes: images deleted, all container work now goes through workerq, and VHDX compaction is requested in QUESTION 0003.

## Recommended E1 start

1. Edit format: don't ask workers for raw unified diffs. Use search/replace blocks (or whole-function replacement) validated by `leakproof/patching.py`, with the diff produced by us.
2. Worker loop on Juliet first: N=4 Lightning workers per case (thinking on, with a reasoning budget — attempt 2 burned 8K tokens and emitted nothing), checkpoint/branch via LocalDockerRunner. Gate v0 = bad build trips → patched build clean under the leak-sensitive configuration → good build still clean → diff touches only the case file.
3. Then 5 ARVO cases (UAF/double free/overflow), one image on disk at a time, run through workerq.
4. Ultra planner only after the worker + gate funnel exists, so its value can be measured against Lightning-only.
