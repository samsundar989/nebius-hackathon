# Leakproof

**Verified fixes, or nothing.** Leakproof is an agent that fixes memory-safety defects in C, C++ and CUDA code — leaks, use-after-free, double free, buffer overflows, data races — and reports a fix only when an evidence gate verifies it. NVIDIA Nemotron models on Nebius Token Factory find the root cause and write the patches; a separate gate process, with the network off, decides.

Every number below is generated from run records by scripts; the full tables are in [docs/NUMBERS.md](docs/NUMBERS.md).

## The problem

Sanitizers and fuzzers find memory bugs faster than teams can fix them: a project can sit on hundreds of open reports. LLMs can write patches, but most "fixes" only make the crash go away — clamp a bound, skip a code path, allocate one more byte — and a repair loop that stops at "the sanitizer is quiet" reports those as successes. Leakproof's job is the opposite: say "fixed" only with evidence a reviewer can check, and say "refused, here is why" otherwise.

## Results

| | cases | crash gone ("raw") | **verified** | model $ per verified fix |
|---|---|---|---|---|
| ARVO — real OSS-Fuzz bugs in 13 projects (r1) | 27 | 18 | **15** | $0.070 |
| Juliet CWE-401 sample (synthetic) | 100 | 94 | **94** (every reproducible case) | $0.011 |
| CUDA on a Kaggle T4 (compute-sanitizer) | 3 | 3 | **3** | $0.007 |

- **The gap between "crash gone" and "verified" is the point.** On ARVO, 18 candidates made the proof-of-concept stop crashing; 3 of those cases were still not fixed — re-fuzzing with enlarged inputs found the same bug again (libplist, jq, libical), and in each case the developer's real fix is clean on that same input.
- **The gate accepts the developers' own fixes**: 24 of 27 upstream fix commits verify when run through the identical gate; one more is rejected *correctly* — it leaks (mosquitto, the leak is allocated on a line that fix adds); 2 are false rejects (7.4%), both from known limits listed below. Raw before review: 24/33.
- **CUDA:** of four candidate patches for an out-of-bounds write, two silenced compute-sanitizer — one clamped the bound, one allocated an extra element — and printed the wrong checksum. Only the output check caught them.
- **Ultra's diagnosis** names a file the developer changed in 22 of 24 ARVO cases (a proxy measure; see NUMBERS.md).
- A second ARVO run with edit fallbacks and one repair round (r2) is reported separately, never merged into r1: see [docs/NUMBERS.md](docs/NUMBERS.md).

## How it works

```
finding ──► baseline build + reproduction (ASan/LSan/UBSan, or compute-sanitizer)
        ──► Nemotron 3 Ultra: root cause + up to 4 fix hypotheses
        ──► 4 × Nemotron 3.5 Lightning workers, each on its own branch of the baseline checkpoint
        ──► the gate, in its own process, network off  ──►  verified | refused (with the reason)
                                                  └─ no verified fix? one repair round: Ultra sees
                                                     each attempt's diff and why it failed
```

Workers see the finding, the plan and the source files they may edit — never the gate's corpus, fuzzing settings, tests, or the developer's fix. A test fails if any module on the worker path imports gate code.

## The evidence gate

A candidate is **verified** only if every check passes:

| check | what it rejects |
|---|---|
| unpatched trips | a baseline that does not reproduce the bug (nothing to judge) |
| diff scope | edits to tests, build files, the fuzz harness (found by content, not directory), sanitizer options, added `exit`/`abort`, allocator tricks |
| build + "compiled" | a build that skipped the edited file: the harness binary's hash must change |
| patched | the proof-of-concept still crashes, or now crashes differently |
| project tests | the project's own suite fails (Juliet: the good-path build stays clean) |
| behaviour | output changed on the reproducer (Juliet, CUDA checksums) |
| differential corpus | a corpus input that ran clean now crashes or changes its exit code or output |
| amplified re-fuzz | enlarged copies of the PoC (every digit/letter run ×2/×8/×64, the whole input, the last element) and 90 s of libFuzzer find a crash the developer's fix does not have |
| safe-fix | the corpus under LeakSanitizer shows a leak, use-after-free or double free the reference does not |

**How a gate lies — bugs we found in our own gate and fixed** (each in [docs/DECISIONS.md](docs/DECISIONS.md)):
- *The patch was never compiled.* Copied-in sources had older timestamps than the objects, so `make` skipped them; the gate "verified" the unpatched binary. Now the harness hash must change.
- *The fuzzer never ran.* ARVO hard-codes AFL/honggfuzz engines; our libFuzzer flags were silently ignored and re-fuzzing "passed" with zero executions. Now every build uses libFuzzer and a run with no executions is inconclusive.
- *A slow input counted as a crash.* A libFuzzer `slow-unit` file rejected a correct fix.
- *Line numbers moved.* A pre-existing bug two lines below the developer's edit was blamed on the fix; crashes are now compared by kind + function + file.
- *The model could edit the harness.* Harnesses outside `fuzz/` directories were editable; files defining the fuzz entry point are now off limits wherever they live.
- *Build scripts run once.* OSS-Fuzz `build.sh` scripts fail the second time (`mkdir build`), so every candidate "failed to build".

The gate was calibrated on the developers' own fixes after each change; the numbers above are from the final gate.

## How we use NVIDIA Nemotron

| model (Nebius Token Factory) | role |
|---|---|
| Nemotron 3 Ultra | root cause and fix hypotheses; repair round with each attempt's failure and the whole hot files |
| Nemotron 3.5 Lightning | the four parallel workers that write edits; advisory reviewer notes |
| Nemotron 3 Super | alternative planner (leaderboard) |

On the synthetic Juliet subset the planner barely matters (Lightning-only 93%, Ultra 95%, Super 93% verified). **On real code it does:** on 10 calibrated ARVO cases, workers without a plan verified 2, with Super 4, with Ultra 7 — and Ultra was cheaper per verified fix than no planner ($0.059 vs $0.112), because failed attempts cost money too (one repeat; see NUMBERS.md). The advisory reviewer flags verified and rejected candidates at about the same rate, so it is shown as notes and never counted as evidence.

## How we use Nebius

- **Token Factory** for every model call, with thinking control and structured outputs. Every call is metered into a cost ledger; on 2026-10-24 the ledger's model spend ($3.28) matched the billing page ($3.27).
- **Sandboxes** (beta) through a small REST client: the gate runs with `networking.enabled=false`, workers branch from one saved checkpoint, and each case records its checkpoint lineage. The Juliet runs used it (100 reproductions in 41 s, 8 in parallel). ARVO images do not import yet (`NotImplementedError: chmod: follow_symlinks unavailable on this platform`), so ARVO runs on local Docker — details in [docs/FEEDBACK.md](docs/FEEDBACK.md).

## Use it on your own project

```toml
# leakproof.toml
[project]
name = "csvsplit"
build = "make all"                       # $CC/$CFLAGS carry the sanitizer flags
reproduce = "./csvsplit_fuzz /tmp/poc"   # must trip a sanitizer before the fix
test = "make test"
harness = "csvsplit_fuzz"                # optional: enables corpus, re-fuzz and LSan checks
poc = "poc.csv"
editable = ["src/*.c", "src/*.h"]
```

```
uv run leakproof fix   --config examples/csvsplit/leakproof.toml
uv run leakproof batch --config examples/csvsplit/leakproof.toml --findings examples/csvsplit/findings
```

`batch` is triage at scale: it reproduces every crash input on one build, groups them by signature (defect kind + top in-project frames), fixes one per group, and re-runs every member's input against the winning patch. On the demo: 10 inputs → 6 crashes → 1 group → fixed once, all 6 clean ($0.009).

## Setup

Python 3.12 and [uv](https://docs.astral.sh/uv/); Docker for the ARVO and bring-your-own runners. Copy `.env.example` to `.env` and fill in `NEBIUS_API_KEY`, `NEBIUS_PROJECT_ID`, `LEAKPROOF_BUDGET_USD`. Then `uv sync` and `uv run pytest -q -m "not network and not docker and not contree"`.

## Cost

All model calls in the project, failed runs and experiments included, are in `runs/cost_ledger.jsonl` and summed in [docs/NUMBERS.md](docs/NUMBERS.md). Sandboxes are recorded as units: they were not billed during the beta.

## Limitations

- ARVO has no memory-leak cases; leak results come from Juliet, which is synthetic.
- The gate shows that the reported crash is gone and that no new sanitizer report appears on the inputs it tries. It cannot prove a fix correct for every input; for example, a verified libplist fix copies a token into a stack array sized by its length, which a very large input could exhaust.
- Calibration false rejects (2 of 27): a strict rule for patches that remove a `free` fired on an older leak; an assert the original crash used to mask was blamed on the fix.
- 14 of the 41 ARVO cases we tried cannot be calibrated: the fix is in the fuzz harness, the fix commit does not stand alone, or the build needs network access.
- The live demo service runs model-written code as an unprivileged user with a clean environment, but cannot disable networking on its host.
- CUDA runs on Kaggle, not on Nebius.

## Feedback on the tools

[docs/FEEDBACK.md](docs/FEEDBACK.md): what worked, what needs work, and exact error strings for Token Factory, Sandboxes and the Batch API.

## License

MIT — see [LICENSE](LICENSE).
