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

### Engine fixes found by smoke runs (before the 60-case run)
1. Behavior check read truncated stdout: LSan/ASan exit without flushing stdio, so the unpatched reference printed 0 bytes. Reference now comes from a `detect_leaks=0`, `stdbuf -o0` run (D-0038).
2. Lightning spent its whole 6K-token budget counting indentation (5/7 failed calls hit `finish_reason=length`). Prompt now says matching ignores whitespace and to think briefly; smoke went from 1/3 to 5/6 verified.
3. Edit application: models prefix paths (`src/x.c`), copy the prompt example's path and code, re-indent blocks, and drop comment lines when quoting. Handled by basename/single-file mapping, re-indentation, and a code-lines-only fallback (unique match required).
4. The planner often returns one hypothesis; the fan-out now always runs N workers (cycling hypotheses), so one formatting slip doesn't sink a case.

### Spend
Token Factory ledger total **$0.8458** of the $25 week cap (E0 $0.0116; E1 smoke runs $0.0921; Juliet 60 $0.7422).

### Blockers
None. Open: `NEBIUS_AI_PROJECT` in `.env` holds the AI Cloud id although CLAUDE.md says it equals the Token Factory id (NOTE 0010; not touched).
