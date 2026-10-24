# REPORT — Leakproof E1 "SHIP" (daily log)

Kickoff: `docs/kickoff/KICKOFF_PROMPT_2026-10-22_LEAKPROOF_E1_SHIP.md`. One section per day: done · numbers · spend · blockers · tomorrow. Every number here comes from `runs/` JSON via a script named next to it.

## Day 1–2 · Thu 2026-10-23 (Phase 1: loop v1)

### Done
- **Fix loop v1, end to end** (commits `4a1e1f7`…): `leakproof/cases/` (Juliet + ARVO adapters behind one interface), `planner.py` (Nemotron 3 Ultra, thinking on, structured output with enums/strings only), `worker.py` (Nemotron 3.5 Lightning, thinking on, search/replace edit blocks; one retry each for an edit that does not apply, a compiler error, and an empty or token-capped reply), `branch.py` (fan-out ≤ 4 from a saved baseline checkpoint, each candidate built in its own container), `gate.py` v0 as a separate process (unpatched trips · patched clean · tests · Juliet behavior · diff-scope), `fix.py` (funnel JSON per case), `scripts/fix_batch.py`, `scripts/run_report.py`.
- **Workers never see the gate**: Juliet workers see the bad path only (reference-fix block and `main()` replaced by markers, D-0037); the gate is a subprocess that `worker.py` never imports; ARVO harness/test files are not shown as editable and the gate rejects edits to them.
- **ARVO shortlist verified** against the local `arvo.db` (v3.0.0): all 26 Tier-1 ids present, project and `crash_type` match on every row. Corrected 32 fields: 7 null `fuzz_target`s filled, h3 375220555 `fuzz_target` was wrong (`fuzzerPolygonToCellsExperimental` → `…NoHoles`), and `fix_commit` filled on the rows that had none (list in the JSON under `verified_against_local_db`). No two Tier-1 rows share a fix commit.
- Environment (D-0036): this session is Windows-native; Windows `uv` with `.venv-win`, datasets copied to `%USERPROFILE%\.cache\leakproof`, container work through workerq via `scripts/lp_job.ps1`. **C: has 198 GB free** (E0 ended at 18 GB), so the disk stop-rule (< 10 GB) is far away; the one-ARVO-image-at-a-time rule still applies.
- **Sandboxes access is live** (found because the Contree contract test stopped skipping): `/whoami` returns every permission `true` with the Token Factory project id and still all `false` with the AI Cloud id. Logged in FEEDBACK.md and HUMAN.md NOTE 0010. REST backend (kickoff rule 2) is scheduled after the ARVO part of Phase 1.

### Numbers — Juliet smoke set, 60 cases (`runs/e1_juliet60_v1`, `scripts/run_report.py e1_juliet60_v1`)
Ultra planner + 4 Lightning workers per case, gate v0, 3 cases in parallel.

| CWE | cases | crash gone (raw) | verified | rejected | no candidate | error |
|---|---|---|---|---|---|---|
| CWE-401 leak | 30 | 29 | 29 | 0 | 0 | 1 |
| CWE-415 double free | 15 | 15 | 15 | 0 | 0 | 0 |
| CWE-416 use after free | 15 | 12 | 12 | 1 | 1 | 1 |
| **all** | **60** | **56** | **56 (93%)** | 1 | 1 | 2 |

- The 2 `error` rows are the two cases E0 could not reproduce (D-0021: global-reachable leak; UAF read inside uninstrumented `wprintf`); the loop crashed on their missing finding. Fixed: they are now recorded as `inconclusive:not_reproducible` with no model spend and stay in the denominator. Verified on reproducible cases: **56/58**.
- **The gate earned its keep at worker level**: of 232 worker candidates, 176 verified; **10 candidates "fixed" a use-after-free by deleting the `free()`** — the crash went away and LSan then reported a new leak, so the gate rejected them (`rejected:new_leak`); 1 still crashed (UAF moved into `printLine`); 1 hit diff-scope. In each of those cases another worker's real fix was verified. Raw "crash gone" and verified are equal at case level because every case had at least one honest candidate.
- The other 44 non-verified workers failed on the edit format, not on judgment the gate could test: 22 SEARCH text not found in the file (after both retries), 18 truncated or unterminated edit blocks (token cap), 1 edit to a file outside its scope, 3 build failures. The edit format is the next lever if the ARVO cases show the same pattern.
- Cost: **$0.7422 for 60 cases → $0.0133 per verified fix** (Ultra $0.45 / Lightning $0.39 across all runs so far). Latency: planner p50 5.0 s, worker LLM time p50 33.7 s, case wall p50 77 s, max 172 s; batch wall 26.6 min.
- Caveat (goes in Limitations): Juliet marks its flaws with `POTENTIAL FLAW` comments and is synthetic; this proves the engine and the gate, not real-world skill. That is what the ARVO cases are for.

### Numbers — ARVO mosquitto 42520955 + jq 42530604 (four runs; only run 4 counts)
Real multi-file C projects, one `n132/arvo` image on disk at a time, `rmi` after each case. Run 4 (`runs/e1_arvo2_v4`, `scripts/run_report.py e1_arvo2_v4`):

| case | ARVO label | reproduced (-O0) | verdict | winning change | gate evidence | $ | wall |
|---|---|---|---|---|---|---|---|
| mosquitto 42520955 | Heap-use-after-free READ 2 | UAF `src/conf.c:2098` | **verified** | save `default_listener`'s index before `realloc` of `config->listeners`, re-point after (4/4 workers, same idea as Ultra's root cause) | unpatched trips · harness relinked (hash changed) · PoC clean · diff-scope · **tests skipped: no runnable suite in the image** (test/unit needs CUnit; the gate runs offline) | 0.0384 | 135 s |
| jq 42530604 | Heap-buffer-overflow WRITE 1 | HBO `decNumber.c:3764` | **verified (gate v0) — suspected false verify** | copy `decNumberToString` output via a fixed `JVP_DTOA_FMT_MAX_LEN` stack buffer, then heap-allocate `strlen+1` | unpatched trips · harness relinked · PoC clean · 7/7 baseline-passing jq suites pass under ASan · diff-scope | 0.0273 | 166 s |

- **jq run 4's winner is probably unsafe**: jq keeps a number literal's full precision, so a literal with more digits than the stack buffer should overflow it. Neither the PoC nor the test suite has such a literal, so gate v0 cannot see it. This is the class Phase 2's differential corpus and re-fuzz exist for; it stays in the tables as "verified (v0)" with this note until gate v1 re-judges it, and becomes the demo of "v0 verified, v1 rejects" if re-fuzz catches it. In run 2 two workers made the minimal fix (`digits + 14` → `digits + 17`), verified with the same evidence.
- Run-to-run variance on jq: verified (run 2, size fix), rejected (run 3: two compiled candidates still overflowed, one moved the crash to line 3758), verified (run 4). The leaderboard will need repeats, not single runs.
- Ultra's root cause was right on both cases in every run (mosquitto: `default_listener` dangling after `realloc`; jq: buffer `digits + 14` too small for `decToString`). The losses were in workers and in our harness, not in planning.

**Runs 1–3 are void, and why matters (D-0041, D-0042):**
1. Run 1: jq's 7/7 passing tests were read as failed: the gate's output sections were split on line-start markers, and a file without a trailing newline swallowed the next marker. Fixed (separator carries its own newline; unit test).
2. Runs 1–2: mosquitto candidates "still crashed" at the original line although one inserted 4 lines above it, and the gate "rebuilt" in 3.45 s vs 20 s for a real build. Run 3 added a gate check that the harness binary's hash must change after a patched build → `inconclusive:patch_not_compiled`. Cause: `fuzzing/broker/Makefile` links `broker_fuzz_test_config` from its `.cpp` only, so an existing binary is never relinked when `mosquitto_broker.a` changes; and make never rebuilds objects when only CFLAGS change, so our "-O0 baseline" for mosquitto was really the image's -O1 harness. Fix: delete the harness before every build and the objects before the baseline build. **Without the hash check, a gate would have reported a real fix as "still crashes"; with a different bug it could equally have reported a non-fix as clean.** The hash check stays as a permanent gate item.
3. Worker cap raised to 12K tokens for ARVO (D-0040): at 6K, 3 of 4 mosquitto workers ran out mid-fix.

Worker losses on real code are still mostly the edit format: in run 4, 2 of 8 workers hit 12K tokens or wrote unterminated blocks, 1 failed to build after its retry.

### Engine fixes found by smoke runs (before the 60-case run)
1. Behavior check read truncated stdout: LSan/ASan exit without flushing stdio, so the unpatched reference printed 0 bytes. Reference now comes from a `detect_leaks=0`, `stdbuf -o0` run (D-0038).
2. Lightning spent its whole 6K-token budget counting indentation (5/7 failed calls hit `finish_reason=length`). Prompt now says matching ignores whitespace and to think briefly; smoke went from 1/3 to 5/6 verified.
3. Edit application: models prefix paths (`src/x.c`), copy the prompt example's path and code, re-indent blocks, and drop comment lines when quoting. Handled by basename/single-file mapping, re-indentation, and a code-lines-only fallback (unique match required).
4. The planner often returns one hypothesis; the fan-out now always runs N workers (cycling hypotheses), so one formatting slip doesn't sink a case.

### Spend
Token Factory ledger total **$1.2201** of the $25 week cap (E0 $0.0116; E1 Juliet smoke runs $0.0921; Juliet 60 $0.7422; ARVO runs 1–4 $0.3742, of which run 4 $0.0657).

### Blockers
None. Open: `NEBIUS_AI_PROJECT` in `.env` holds the AI Cloud id although CLAUDE.md says it equals the Token Factory id (NOTE 0010; not touched).

### Phase 1 exit (kickoff §3)
- Juliet ≥ 50% verified with Lightning workers: **met, 56/60 (93%)**.
- Both ARVO cases produce an honest funnel: **met** (both verified in run 4 with the hash-proven gate; jq flagged as a suspected false verify pending gate v1; mosquitto's tests are unavailable and shown as skipped).

### Tomorrow (Fri Oct 24 → Phase 2)
1. Gate v1: differential corpus, re-fuzz 60–120 s, safe-fix (leak-sensitive), audit flag (Nano). First test: re-judge jq run 4's winner.
2. Sandboxes REST backend (≤ 2 h, behind a flag; access is live).
3. Juliet CWE-401 sample (100) and the ARVO Tier-1 batch (26 cases, 20 min box each), then the model leaderboard.
4. Edit format: keep comment lines the model omitted from SEARCH in the code-lines fallback (bundles should not delete upstream comments).

## Day 3 · Thu 2026-10-23 night (Phase 2 start: housekeeping + P0 gate v1)

### Done
- Strategy docs untracked (`docs/research/`, `docs/kickoff/` gitignored; files stay local); QUESTION 0012 (one-time history rewrite before going public) asked, default no.
- CI red → green: `ruff format` on `scripts/arvo_inspect.py`; 4 cp1252 bytes in `docs/FEEDBACK.md` re-encoded; `tests/test_docs_encoding.py` fails on invalid UTF-8 / U+FFFD in tracked `README.md` + `docs/**/*.md`.
- **Gate v1** (D-0043, D-0044): checks 5 differential corpus, 6 refuzz (amplified PoC variants first, then libFuzzer 90 s, `-max_len ≥ 8×PoC`), 7 safe-fix (corpus under LSan). A refuzz crash is blamed on the patch unless the baseline crashes identically on that input away from the target; the input + report are saved under `gate_artifacts/`. `scripts/rejudge.py` re-gates saved candidates at $0.
- Machine note: the host ran out of commit charge (another project's jobs held ~25 GB) and WSL2/Docker crashed; nothing of ours was running. All gate runs since went through workerq.

### P0 acceptance (kickoff addendum §3)
| case · candidate | v0 | v1 | evidence |
|---|---|---|---|
| jq 42530604 · run 4 winner (`char buffer[JVP_DTOA_FMT_MAX_LEN]`) | verified | **rejected:refuzz_new_crash** | stack-buffer-overflow `decNumber.c:3724` from **amplification `digits1_x64`** (149 B; baseline gives the original heap overflow there) — `runs/p0_v1b_arvo` |
| jq 42530604 · run 2 (`digits + 17`) | verified | **verified** | 14 variants clean; libFuzzer 90 s, 2.6M execs, no crash; 33 corpus inputs identical; LSan clean |
| mosquitto 42520955 · run 4, 4 candidates | verified ×4 | **verified ×4** | 197 seed-corpus inputs identical, LSan clean; refuzz hit only the pre-existing `memory_mosq.c:78` crash (baseline identical, not attributed) |
| mosquitto 42520955 · run 2, 2 candidates | rejected:still_crashes (void, D-0041) | **verified ×2** | same as above; v0 verdicts were void (patch never linked) |
| Juliet 60 (57 cases with candidates, 152 candidates) | 56 verified | **56 verified** | 151/152 verdicts unchanged; checks 5–7 skipped (no input). The one change (`malloc_free_int_15` H4: diff_scope → new_leak) is 75a4b9c's alloc-guard rule, not v1 — `runs/p0_v1_juliet60` |

How we got there (honest order): the first v1 run (`runs/p0_rejudge_jq`, `runs/p0_v1_arvo`) also rejected jq run 4, but **via libFuzzer** (116-byte input after 1,975 execs), not amplification: the PoC is `-16E-1061947065` and only its longest digit run (the exponent) was amplified. The same run rejected 3 of 4 mosquitto run-4 candidates because a 6 KB log tail cut the `==ERROR:` header off a long UAF report (`exit_1 at ?`). Both fixed in D-0044 (every digit/alpha run amplified; reports captured from the ERROR line), then re-run.

### Numbers that changed
- jq 42530604 case verdict (run 4): verified → **verified via the run-2 fix only**; run 4's winner is now rejected:refuzz_new_crash.
- mosquitto 42520955 run 2: void → 2/2 verified under v1.
- Juliet 60: unchanged (56/60 verified).
- Gate time per ARVO candidate: v0 ~21 s → v1 24–114 s (jq; refuzz 90 s when nothing crashes). Spend: $0 (ledger still **$1.2201**).

### CI
Green: runs #3 (c5bbf2a), #4 (a209e04), #5 (2b54e42), #6 (ab418da). #1–#2 were red (format only).

### Open issues
1. **Refuzz attribution is baseline-only** (D-0044): a patch that gets past the original crash and exposes a deeper pre-existing bug looks like a new crash. Seen once: first-run mosquitto w0–w2 hit a heap-use-after-free on a 1000-byte buffer freed in `config__read_file` (`conf.c:2505`); the baseline shows a different crash on that input. In the fixed re-run the fuzzer hit the known `memory_mosq.c:78` bug first instead, so the verdicts depend on which crash libFuzzer meets first. Plan (P1): use the developer fix (`-fix` image) as a second reference, and re-check that saved UAF input (`runs/p0_v1_arvo/42520955/e1_arvo2_v4/gate_artifacts/`) against it.
2. mosquitto refuzz always ends at the pre-existing `memory_mosq.c:78` crash, so its effective fuzzing time is short. Option: `-fork=1 -ignore_crashes=1` and judge every distinct crash.
3. Check 8 (LLM audit flag) not built yet.

## Day 4 · Fri 2026-10-24 (P1: gate calibration with the developers' own fixes)

### Done
- `leakproof/calibrate.py` + `scripts/calibrate.py`: the upstream fix commit (`github.com/<repo>/commit/<sha>.patch`, fetched in preparation, cached outside the repo) applied to the -O0 baseline with `git apply`, gated **exactly like a model candidate** (same editable rule, no strategy exemption, baseline-only attribution). Its build on the baseline becomes a **reference image** for model candidates: refuzz crashes and leaks the developer fix also shows are not blamed on the model. Gate-side only; `tests/test_isolation.py` fails if the worker path imports it.
- Gate hole closed: an edit to any file defining `LLVMFuzzerTestOneInput` fails diff_scope (oniguruma `harnesses/`, lz4 `ossfuzz/`, pcre2 `src/pcre2_fuzzsupport.c` were editable by path before); workers are never shown such files.
- `scripts/calibration_report.py` + `cases/arvo/calibration_adjudication.json` (reviewed, evidence-linked note for each developer fix the gate did not verify).

### Calibration — 26 ARVO Tier-1 cases (`runs/p1_calibration_v3`)
| | raw | adjudicated |
|---|---|---|
| developer fixes gated | 19 | 18 (+1 out of scope) |
| **accepted (verified)** | **15** | **15** |
| true reject (the developer fix has the defect) | — | 1 |
| false reject | 4 (21%) | **2 (11%)** |

- **True reject:** mosquitto 42520883 — the developer's fix for the invalid free leaks: on 21 seed-corpus inputs the baseline is LSan-clean and the fix leaks 15 B allocated by `mosquitto__strdup` at `conf.c:993`, a line the fix adds.
- **False rejects (known limits, not tuned away):** libzip 42520377 — the strict "removed a free ⇒ PoC must be LSan-clean" rule fires on a pre-existing leak (`_zip_read_cdir`, `zip_open.c:305`) that the UAF used to mask; quickjs 42531514 — an amplified input reaches an `assert` in `get_lvalue` that the original overflow masked on the baseline. With the developer fix as reference (the batch setting), model candidates are not exposed to the second one.
- **Not calibratable (8):** fix only in the harness — oniguruma 42517784, lz4 42513177, pcre2 42533629, h3 375220555 (fix renames functions the harness calls); baseline build needs network (`apt` inside build.sh) — libssh2 42535924, 42523626, libbpf 42504164; fix commit does not apply — quickjs 413161375.
- Model candidates re-gated with the reference: jq run 4 winner still `rejected:refuzz_new_crash` (the developer fix is clean on its crashing input); mosquitto 6/6 verified. The saved first-run mosquitto "UAF" inputs crash the developer fix too (`memory_mosq.c:78`): pre-existing.

How the number moved (all three passes kept): v1 10/19 → v2 9/19 → v3 15/19. Causes found from saved evidence, not by loosening checks: (1) OSS-Fuzz `build.sh` is not re-runnable (`mkdir build` on the baseline that already built) → `mkdir` shim in the baseline (D-0047); (2) `/bin/arvo` hard-codes `FUZZING_ENGINE=afl|honggfuzz`, so AFL/honggfuzz harnesses were never really fuzzed (libplist 42519914 "passed" with 0 executions) → we call `compile` with libFuzzer, and no-execution refuzz is `inconclusive` (D-0046/47); (3) leaks behind a baseline crash are "unmasked", not new (D-0046). One rule was relaxed for ARVO only: dropping a `free` is judged by LSan instead of rejected outright.

### Numbers that changed
- Gate v1 → D-0047: jq/mosquitto model verdicts unchanged (jq run 4 winner rejected; run 2 + mosquitto ×6 verified).
- New: gate accepts **15/18** developer fixes (adjudicated; raw 15/19) and rejects 1 developer fix that leaks.
- Spend: $0 (no model calls); ledger still **$1.2201**.

### Open
1. Calibrate Tier-2 + reserves (15 cases) as replacements for the 8 uncalibratable Tier-1 cases → P3 case list.
2. Check 8 (LLM audit flag) not built.
