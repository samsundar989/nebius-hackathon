# Devpost entry (draft, for Samuel to paste)

Numbers come from `docs/NUMBERS.md`; re-check them on Wed Oct 29 before the final edit. Links in [brackets] are filled in once they exist.

**Project name:** Leakproof

**Tagline (≤ 200 chars):** An agent that fixes memory-safety bugs in C, C++ and CUDA, and ships only the fixes an evidence gate verifies. Verified fixes, or nothing.

**Track:** Coding & Agentic Engineering

**Links:** repository [GitHub URL] · live dashboard [Render static site URL] · video [YouTube URL]

---

## Inspiration

Fuzzers find memory bugs faster than maintainers can fix them, and LLMs now write patches for them. The catch: most "fixes" just make the crash go away. They clamp a bound, skip a code path or allocate one more byte, and a repair loop that stops at "the sanitizer is quiet" reports them as wins. Published work finds that checking only the original crash input inflates repair agents' solve rates by about 1.8× (PatchBench). We wanted an agent whose "fixed" you can believe, and whose "not fixed" tells you why.

## What it does

Given a sanitizer finding (a crash input plus a build), Leakproof:

1. builds and reproduces the bug in a sandbox;
2. has **Nemotron 3 Ultra** find the root cause and propose up to four fix hypotheses;
3. has four **Nemotron 3.5 Lightning** workers each write a patch on its own branch of the baseline checkpoint;
4. runs every candidate through an **evidence gate** in a separate process with the network off. A candidate passes only if it rebuilds, actually compiles into the binary, no longer crashes, passes the project's tests, behaves the same on a corpus, survives amplified and fuzzed inputs that the developer's real fix survives, and adds no leak or use-after-free;
5. when several candidates verify, lets Ultra pick the one that best preserves the code's intent;
6. writes an evidence bundle for each case: the diff, every check with its evidence, and the cost.

It works on your own project through a short `leakproof.toml` (`leakproof fix`), triages piles of crash reports (`leakproof batch` clusters them, fixes each cluster once and re-checks every report), and ships a GitHub Action template.

## Results (real numbers, failed runs included)

- **27 real OSS-Fuzz bugs (ARVO, 13 projects):** the crash went away in 18. **15 verified** at $0.070 of model spend per verified fix. Compared by hand with the developers' own fixes, the chosen fix is correct in **14**.
- **The gate isn't just strict:** it accepts 24 of 27 of the developers' own fixes. One rejection is correct (that upstream fix leaks).
- **Gate precision:** 52 of 67 verified patches (78%) are correct when compared with the developer's fix. We publish the 8 that are wrong and explain how each fooled the gate.
- **The planner matters on real code:** same Lightning workers, 10 cases. No planner: 2 verified; Super: 4; Ultra: 7. Ultra was also cheaper per verified fix, because failed attempts cost money too.
- **Juliet CWE-401 (synthetic):** 94/100, every reproducible case, at $0.011 per fix.
- **CUDA (compute-sanitizer on a T4):** 3/3 verified. Two candidate patches silenced the sanitizer but printed the wrong answer; the gate rejected them.

## How we built it

Python 3.12 with the plain `openai` SDK against Nebius Token Factory. There's no agent framework: the loop is planner → workers → gate. Every model call is metered into a cost ledger with a hard budget stop, and the ledger matched the Token Factory billing page to within a cent. The gate runs on local Docker or on **Nebius Sandboxes** with `networking.enabled=false`. We wrote a small REST runner because the SDK has no networking switch. Workers branch from one saved checkpoint. A unit test fails if any worker-side module imports gate code, so workers can never see the tests, the corpus or the developer's fix. ARVO supplies reproducible OSS-Fuzz bugs; we calibrate the gate by running the developers' own fix commits through it.

## Challenges we ran into

Our own gate lied to us, seven different ways (all in the README's "How a gate lies"):
- it "verified" binaries the patch never compiled into;
- its fuzzer silently never ran;
- a slow input counted as a crash;
- the model could edit the fuzz harness;
- OSS-Fuzz build scripts can't run twice;
- line numbers moved under a pre-existing bug;
- a fuzz harness can only see what it prints. Two mosquitto patches passed every check yet pointed the config at the wrong listener.

Each fix was re-calibrated against the developers' own patches.

## Accomplishments that we're proud of

Honest numbers: raw versus verified versus correct, side by side, regenerated from run records by scripts. The 8 wrong-but-verified patches we found are published, not hidden.

## What we learned

"The crash is gone" is cheap, and "correct" is expensive to prove. Enlarging the input (×2, ×8, ×64 digit runs) catches a surprising share of fake fixes. On real code a strong planner pays for itself. Thinking-off modes save tokens but give wrong answers on reasoning tasks.

## What's next

Run the project test suites the OSS-Fuzz images lack (with their dependencies installed while preparing the baseline). Run the GitHub Action on a real repository. Move ARVO to Sandboxes once its image importer handles symlinked layers.

## Built with

nvidia-nemotron, nemotron-3-ultra, nemotron-3.5-lightning, nemotron-3-super, nebius-token-factory, nebius-sandboxes, python, docker, addresssanitizer, leaksanitizer, libfuzzer, oss-fuzz, arvo, compute-sanitizer, cuda, kaggle, render, github-actions

## Feedback for Nebius and NVIDIA (short form; full version in docs/FEEDBACK.md)

- **Token Factory:** truly OpenAI-compatible; rate limits (600 RPM) are far above folklore; thinking control works through `chat_template_kwargs`. Needs work: `json_schema` numeric fields can decode digit by digit until `max_tokens`; `reasoning_effort` levels are ignored except on Super; the Batch API returned "temporarily unavailable"; there's no cost field in responses.
- **Sandboxes:** the checkpoint-and-branch model fits "baseline → N candidates → gate" exactly, and `networking.enabled=false` is honoured. Needs work: the SDK lacks the networking field; "not approved" returns 200 with all permissions false; the importer fails on older images with `NotImplementedError: chmod: follow_symlinks unavailable on this platform`; two different "project id" formats.
- **Nemotron:** Ultra is a strong planner and a useful first-pass reviewer (we overrode 8 of its 67 judgments). Lightning is a fast, cheap patch worker when its thinking budget is bounded.
- **compute-sanitizer:** exact reports, but the exit code is 0 on errors unless `--error-exitcode` is set, and it cannot attach under WSL2 yet prints a clean-looking report.

## Gallery images (to capture)

1. Dashboard first screen (headline numbers, jq refusal card, planner card).
2. A case page with the gate matrix (mosquitto 42520955, with "other verified candidates" open).
3. `docs/architecture.svg`.
4. Terminal: `leakproof batch` → "1 cluster, all 6 members clean".
