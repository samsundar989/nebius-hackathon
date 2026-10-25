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

### P1 final — 41 ARVO cases (Tier-1 + Tier-2 + reserves), gate after D-0049
| | raw | adjudicated |
|---|---|---|
| developer fixes gated | 33 | 27 countable |
| **accepted (verified)** | **24** | **24** |
| true reject (developer fix leaks) | — | 1 (mosquitto 42520883) |
| false reject | 9 (27%) | **2 (7.4%)** — libzip 42520377, quickjs 42531514 |
| not countable | 8 | 14: harness-only fix 4, fix commit not standalone 5, does not apply 2, baseline needs network 3 |

- One more gate bug found and fixed on the way (D-0049): refuzz attribution compared exact lines, so a pre-existing crash a few lines below the developer's edit was blamed on the fix (libucl 42512369 `:2152`→`:2154`, libexif 42500232 `:126`→`:132`). Now compared by kind + function + file; both re-run → verified. Checked that no other verdict could change.
- **P3 batch list**: `cases/arvo/batch_p3.json` — 27 calibrated cases (Tier-1 18, Tier-2 2, reserves 7), each with a developer-fix reference for attribution.
- Headline sentence the data supports: *"Our gate accepts 24 of 27 developer fixes (and rejects one that leaks), and rejects the model candidate that only silenced jq's crash."* The model-side reject count comes from P3.

## Day 4 (cont.) · Sat 2026-10-24 — P2, P3 r1, P4 Juliet ×100, P5 pieces; strategist review #2

Strategist notes 2026-10-24 15:50 CDT: read, acting on A (done: units relabel, Juliet re-run, site committed) → B1–B3 (done, D-0058/D-0059) → B4 P3 r2 (smoke running; batch capped at $1.95 pending QUESTION 0015).

### P3 r1 — 27 calibrated ARVO cases, gate v1 + developer-fix reference (`runs/p3_arvo27_r1`)
| | as run | after D-0056 correction |
|---|---|---|
| raw: PoC no longer crashes | 18/27 | 18/27 |
| v0: checks 1–4 | 18/27 | 18/27 |
| **v1 verified** | 14/27 (51.9%) | **15/27 (55.6%)** |
| model $ / verified fix | $0.0747 | $0.0697 |

The correction: jq 42531297's candidates were rejected on a libFuzzer `slow-unit-*` artifact (exit 0, no crash); the gate now takes only crash-type artifacts (D-0056), every other refuzz verdict was checked (only this case used one), and its re-judge (`runs/p3_rejudge_d0056`) is verified. The other three "crash gone but rejected" cases are real: libplist 42519914 (UAF at the target function on a fuzzed input), jq 42530604 (`decToString` overflow on an amplified input), libical 42536390 (UAF at the target on `whole_x64`; one candidate leaks) — in each the developer fix is clean on the same input.

### Juliet CWE-401 ×100 (`runs/p4_juliet401x100_r1`, Nebius Sandboxes, 8 in parallel)
**94/100 verified** — all 94 reproducible cases; 6 not reproducible (4 leaks reachable from a global at exit, 2 class-based cases our build cannot link). Model spend $1.0139 → **$0.0108 per verified fix**; 1.23 sandbox units. First pass lost 22 cases to a ledger race (D-0054), re-run on Sandboxes.

### Platform
- Sandboxes REST backend (D-0053): networking off honoured, contract suite 8/8, Juliet end to end with lineage. ARVO images fail to import (`NotImplementedError: chmod: follow_symlinks unavailable`), so ARVO stays on Docker.
- Billing (ANSWER 0013): Sandboxes not billed during the beta; **ledger model spend $3.28 vs Nebius billing $3.27**. Sandboxes compute is now `units` (D-0057).

### Product pieces
Bring-your-own adapter + `leakproof fix --config` + `examples/csvsplit` (D-0055; live demo run pending Docker), evidence bundles (`scripts/render_bundle.py`), static dashboard (`site/`, generated by `scripts/build_site.py`), Render Blueprint with the demo service shipped live-off (`render.yaml`, `service/`).

### Numbers that changed
- P3 r1 verified 14 → **15/27** (D-0056 correction).
- Juliet CWE-401 ×100: 72/100 (22 errors) → **94/100**.
- Spend: model **$3.28** total; sandbox units 3.23 (not $).

### CI
Red on d55c8da/afaff4c (a smoke-set test assumed only 60 Juliet case files; fixed in 5427caf); the Actions page has been unreachable from the browser since, so later runs are unconfirmed; the full suite (262 tests) passes locally on every commit.

## Day 4 (evening) · Sat 2026-10-24 — B4 (P3 r2), C, D, E, README/video drafts

Strategist notes 2026-10-24 15:50 CDT: still the newest entry; acting on B4 (r2 paused at the $1.95 cap, QUESTION 0015), C (done), D (done except Render apply = QUESTION 0011), E (done), Monday items started early (README draft, §7 rewording, video script).

### P3 r2 (edit fallbacks + one repair round; `runs/p3_arvo27_r2`) — 18/27 cases run before the cap
Same 18 cases: r1 8 verified → **r2 9** (7 in round 1 + 2 recovered by the repair round: md4c 42507297, libplist 42507851). Gained md4c 42507297, libzip 42520377, jq 42530604; lost mosquitto 42522195 and jq 42531297 — run-to-run variance in both directions. Workers without an applicable edit: 30/80 (r1 40/108): the fallbacks alone did not move the rate; two worker-side fixes followed (D-0062 brace balance, D-0065 diff-shaped replies), effective after r2. The other 9 cases await ANSWER 0015.

### C — evidence quality
- Juliet leaderboard (20 cases × 3 repeats): Lightning-only 93%, Ultra 95%, Super 93%; $/verified $0.0042 / $0.0142 / $0.0080. ARVO leaderboard (10 cases, round 1 only) running: Lightning-only **2/10** verified.
- Ultra root cause vs developer fix (proxy): file 22/24, function 14/22.
- Audit flag: does not separate verified from rejected (ARVO 83% vs 79%) → "advisory reviewer notes" (D-0060).

### D — product surface
- CUDA on a Kaggle T4: **3/3 verified**; 2 candidates `silenced_only` (clamp, over-allocate) caught by the checksum (D-0063).
- Bundles for every case (refused ones lead with the reason); dashboard CUDA panel; demo service live path sandboxed (`nobody`, clean env), live smoke 3/3 verified, key isolation verified (D-0061, D-0067) → QUESTION 0011.

### E — triage at scale
`leakproof batch`: csvsplit 10 inputs → 6 crash → 1 cluster → fixed once, all 6 members clean, $0.0094 (D-0064, D-0066). `leakproof fix` on csvsplit: verified, $0.0100.

### Numbers that changed
- Juliet leaderboard and ARVO r2 (partial) are new; P3 r1 stays 15/27; calibration stays 24/27.
- Model spend total: see `docs/NUMBERS.md` (generated); sandbox units separate.

### CI
Not verifiable from here since the Actions page went 404 in the browser; 266 tests pass locally on every push.

## Day 5 · Sat night 2026-10-24 → Sun 2026-10-25 — review #4 orders 1–3, 5, 6

Strategist notes 2026-10-24 22:05 CDT (review #4): acknowledged; executed orders 1 (CI), 2a–d and 2f (semantic audit, adjudication, strict tier, winner selection, README item), 3 (dashboard), 5 (README) and 6 (video script v2); 2e (test suites) and 4 (headline naming) in progress.

### CI
`leakproof/cli.py` reformatted; `.githooks/pre-commit` now runs `ruff format --check` and `ruff check` after the secret scan, so a lint-red push cannot happen from this checkout.

### Is a verified fix correct? (D-0069, D-0071)
- 67 distinct verified ARVO diffs (95 candidates; P3 run 1, run 2, three `lb_arvo_*` runs) classified by Ultra against the developer's fix ($0.67), then all reviewed by hand: **52/67 correct** (16 equivalent, 36 different but correct), 7 defensive, **8 wrong**. Gate precision 78%.
- Ultra was overridden 8 times; the important one: mosquitto 42522195 (Ultra planner run) — Ultra called it "different but correct", but the patch reads and throws away the first line of every config file before parsing, which is why the PoC stops crashing. Four "defensive" calls were in fact bounded fixes in the developer's own function.
- Strict tier ("verified, and the chosen fix is correct"): run 1 **14/27**, run 2 8/18; planners on real code: none 2, Super 3, Ultra 5 of 10.

### Winner selection (D-0070)
- Pairwise Ultra review in both orders, diff size last ($0.68 for 20 cases with several verified diffs): 10 winners changed; the 3 cases where the smallest-diff rule picked a wrong fix (mosquitto 42520955, libplist 42507851 run 2, libexif 42500216 Super) now pick a correct one; no correct winner was replaced by a wrong one. Without it strict would be 13 (run 1) and 7 (run 2).
- Cross-candidate differential (`scripts/cross_diff.py`, workerq): pcre2 42526932 — 358 inputs (corpus, PoC, amplified, 150 fuzz finds per candidate), candidates agree. The remaining cases are running (job 3818).

### Dashboard and README
- One source: `leakproof/results.py` applies the D-0056 re-judge, D-0070 winners and D-0069 classes; `readme_numbers.py` writes NUMBERS.md and `site/data/numbers.json`, which the dashboard headline reads — the site now says 15/27 and $0.070, like the README.
- First screen (checked at 1440×900): five headline numbers, the jq refusal card, the planner card, "Run a live fix" (disabled until QUESTION 0011). ARVO leaderboard table; calibration as counts with readable labels, cases collapsed; case pages show the semantic class and "other verified candidates"; inline favicon.
- README: links row and badges, the jq "aha" (corrected: the doubled input overflows the *patched* jq; the baseline is clean on it), OSS-Fuzz scale (quoted from its README) and PatchBench's 1.83× (verified on arXiv; the 45–60% figure was not in the abstract and is left out), architecture SVG, strict tier, "The harness can only see what it prints", two showcase bundles.

### Note
A Windows `uv run` without `UV_PROJECT_ENVIRONMENT=.venv-win` tried to replace the WSL `.venv` and may have removed part of it; WSL rebuilds it with `uv sync`.

## Day 5 (cont.) · Sun 2026-10-25, 01:20–04:00 CDT — review #5 orders 1–4, 6

Strategist notes 2026-10-25 01:20 CDT (review #5): acknowledged; orders 1, 2, 3, 4 and 6 done, order 5 (Pages fallback) is due Mon 12:00 only if Render is still not applied.

### 1 — real tests in the gate (D-0073, D-0075)
- mosquitto: CUnit installed in baseline prep (network on for that step only), the unit suite linked with the sanitizer and coverage flags: ~210–240 tests per case, 1 already failing on the baseline. The gate now compares per test when a suite fails on the baseline.
- libexif (12 pass + 1 skip) and libplist (28/28) run `make check` offline. Stopped at 2 extra projects as ordered.
- Re-judged every verified candidate of those 11 cases in all runs ($0): **all still verified, now with tests passing**; headline numbers unchanged (15/27, 14 strict). A first re-judge without the developer-fix reference wrongly rejected libplist 42508524 (a crash the developer's fix shares); `rejudge.py --reference developer` fixed that. The same run caught the wrong libexif 8-byte `memcmp` fix on a fuzz input, which the next run missed: refuzz is a sample.

### 2 — evidence strength (D-0074)
- In 26 of 27 ARVO cases the fuzz harness prints nothing: on real code the differential sees exit codes and crashes only. Evidence is medium where project tests ran, weak elsewhere; none strong.
- Wrong/defensive fixes do **not** concentrate in weak (wrong 6 medium / 2 weak; correct 43 / 9). So per the order's condition the label stays descriptive ("verified, needs human review" on weak) rather than a correctness rule; README "How a gate lies" #7 says so and links NUMBERS.

### 3, 4, 6
- Dashboard: compact diff boxes (changed lines ±2), "Other verified candidates (2): both wrong", evidence badge + legend on case pages (checked in the browser).
- DEVPOST: "Who it's for", updated "What's next". Video: B-roll list; planner strict numbers synced (2/3/5).

### Model spend
$0 since review #5 (all Docker work through workerq, jobs 3820–3828).

## Day 5 (cont.) · Sun 2026-10-25, 07:15–09:40 CDT — review #6

Strategist notes 2026-10-25 07:15 CDT (review #6): acknowledged; orders 1, 2 and 3 done; 4 (Pages fallback) is due Mon 12:00 if Render is still not applied; 5 waits for ANSWER 0015.

### 1 — real open bugs (D-0076, QUESTION 0017)
14 open GitHub issues with ASan reports triaged → 10 configured → 6 reproduce at upstream HEAD → 4 without an open fix PR → 3 verified (berry #544 format, toybox #571, #572) → **1 ready to propose** after Ultra's and my review (toybox #572, H2·w1; the patch applies cleanly to HEAD). Spend $0.70 of the $2.50 cap. On these projects the gate had only the reproducer (no tests wired, no harness), and 6 of 7 distinct verified diffs are wrong or defensive on review; for #572 the pairwise selection picked a wrong candidate over the correct one. Nothing posted upstream.

### 2 — video draft
`video/leakproof_draft.mp4`: 2:55, silent, captions burned in; Playwright recordings of the dashboard and of terminal replays rebuilt from recorded runs, assembled with the ffmpeg bundled in imageio-ffmpeg (both installed into `.venv-win` only). Shot list and captions in `video/`. NOTE 0016 updated.

### 3 — polish
Funnel labels in plain words; FEEDBACK: the re-judge lesson (cross-cutting section).

### Model spend
$0.70 (open bugs) since review #6.

## Day 5 (cont.) · Sun 2026-10-25, 10:25–11:40 CDT — review #7

Strategist notes 2026-10-25 10:25 CDT (review #7): acknowledged; orders 1–5 done; 6 (Pages fallback) is due Mon 12:00 if Render is still not applied.

1. **Video v2** (`video/leakproof_draft.mp4`, 2:49, 1920×1080): terminal scenes at 28 px with ≤ 22 lines and the result line boxed; one dashboard card per scene, zoomed to fill the frame, slow pans; title and end cards (end card numbers read from `site/data`); 40 px captions. Two recording bugs found by pulling frames and fixed: device-scale-factor recording landed in a quarter of the frame, and static stretches recorded too few frames (clips now padded to their exact length). NOTE 0016 updated.
2. **toybox #572 package** (`cases/open_bugs/landley_toybox/572/SUBMISSION.md`): the one-liner and H2·w1 both pass the gate and all 13 of toybox's `patch` tests (D-0077); format-patch with Samuel as author; disclosure states the one-liner came from review. QUESTION 0017 updated.
3. **Devpost assets** (`docs/devpost/`): thumbnail, 5 gallery images at 3:2 2×, architecture PNG; `docs/DEVPOST.md` gained "Try it out" and the open-bugs funnel.
4. **README** "In 60 seconds" box.
5. **Open bugs round 2**: 16 more issues → 3 reproduce at HEAD → 2 verified → 0 ready as written (cNBT defensive with a new NULL dereference on the out-of-memory path; jsmn needs one more guard). Both rounds: 30 → 7 → 5 → 1. $0.22 (total open-bugs spend $0.92).

Model spend for review #7: $0.22.

## Day 5 (cont.) · Sun 2026-10-25, 13:30–14:30 CDT — review #8

Strategist notes 2026-10-25 13:30 CDT (review #8): acknowledged; orders 1, 2, 3 and 5 done; 4 (`leakproof init`) next; 6 (Pages fallback) due Mon 12:00 if Render is still not applied.

1. **Harness-less gate (D-0078)**: generated inputs from the PoC (amplified, 8 truncations, 200 seeded mutations) through the project's own reproducer, patched and unpatched; same-bug / new-crash / pre-existing crash rule; behaviour rule on clean inputs. Re-gate of every verified open-bugs diff ($0): toybox #571's wrong fix is now rejected (`refuzz_same_bug`, 7 of 169 inputs); both correct #572 fixes still verified; four other review findings still missed (table in `cases/open_bugs/REVIEW.md`, README gate section, NUMBERS). Allocation-failure check (advisory): on cNBT #28 it reached only 4 allocations — inconclusive. The "20 Juliet cases" acceptance check does not apply (Juliet programs take no input); D-0078 says so.
2. **Video v3** (2:36): caption band, top-anchored terminal, fix split into plan → verdict and the highlighted diff, calibration summary card, cards at 70–85 % of frame height, 104 px end-card numbers. A blank calibration scene (Playwright records nothing for a static page) was found by pulling frames; card scenes are now screenshots. NOTE 0016: ready for narration.
3. **Devpost gallery**: cards fill the 3:2 canvas (matrix transposed); image 5 is now jq 42531297 (1 verified, 2 refused by re-fuzz); new image 6 (review finding → caught by); arrowhead fixed (an unfilled dashed path rendered as a black triangle); first screen at a narrower viewport without the "not deployed" note.
5. **Before going public** — `git grep` for the email and personal paths:
   - email in `572/0001-…patch` and `572/SUBMISSION.md` → replaced with `<your git identity>`; the real copy is the gitignored `0001-patch.private.patch`; QUESTION 0017 updated.
   - `C:\Users\<user>` in `scripts/lp_job.ps1` and `scripts/service_smoke.ps1` → `%USERPROFILE%`- and `$PSScriptRoot`-relative paths.
   - left as is: `CLAUDE.md` (environment line), `docs/DECISIONS.md` D-0006 (append-only), `docs/HUMAN.md` (a Docker disk path in an old note). `samsundar989` also appears as the GitHub repo owner in README, the GitHub Action example and the video end card: the public repo URL.
   - git history: every commit's author email is the Gmail address, and one earlier version of the patch file has it; not rewritten (QUESTION 0012).
   - Also found: the Sandboxes contract test for relative-path uploads fails today (FEEDBACK); the gate uploads to absolute paths, so verdicts are unaffected.

Model spend for review #8 so far: $0.

