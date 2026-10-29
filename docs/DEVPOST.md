# Devpost entry (draft, for Samuel to paste)

Numbers come from `docs/NUMBERS.md`; re-check them on Wed Oct 29 before the final edit. Links in [brackets] are filled in once they exist.

**Project name:** Leakproof

**Tagline (≤ 200 chars):** An agent that fixes memory-safety bugs in C, C++ and CUDA, and ships only the fixes an evidence gate verifies. Verified fixes, or nothing.

**Track:** Coding & Agentic Engineering

**Links:** repository https://github.com/samsundar989/nebius-hackathon · live dashboard https://leakproof-dashboard.onrender.com · video [YouTube URL]

## Try it out

- Repository: https://github.com/samsundar989/nebius-hackathon — `uv run leakproof fix --config examples/csvsplit/leakproof.toml` (Docker and a Nebius Token Factory key; about one cent per fix).
- Dashboard: https://leakproof-dashboard.onrender.com — every run, every gate check, the calibration and the planner comparison.

**Testing instructions (for the Devpost field):** open the dashboard. **Re-verify without AI** re-runs the whole evidence gate on a stored worker patch from a real run (choose a patch the gate verified or one it rejected) on the demo server, with no model call and no cost, and shows today's verdict next to the original one; it takes under a minute (the free server sleeps when idle, so the first click can take a minute longer to wake it). **Run live** fixes one Juliet case end to end with Nemotron on Nebius Token Factory; enter the passcode **[PASSCODE: Samuel types it on Devpost only, never in this file]** first. Live runs are capped at $0.50 a day and $3 in total; past the cap, or without the passcode, the button shows a labelled recorded run instead.
- Video: [YouTube URL] — 2:50.
- Walkthrough: [docs/WALKTHROUGH.md](https://github.com/samsundar989/nebius-hackathon/blob/main/docs/WALKTHROUGH.md) — from `leakproof init` to a ready-to-send patch on the csvsplit example, with real outputs.

## For judges

| criterion | evidence | where |
|---|---|---|
| Technological implementation | Nemotron 3 Ultra plans, four Nemotron 3.5 Lightning workers patch, Nemotron 3 Super attacks verified candidates, Nemotron 3 Nano drafts configs from bug reports, all on Nebius Token Factory; a separate gate process (Docker or Nebius Sandboxes, network off) decides; every model call is metered | README "How we use" sections; docs/NUMBERS.md |
| Design | a CLI from `init` to `fix` to a ready-to-send `package`; a live dashboard with "Re-verify without AI" (the full gate re-run on a stored patch, no model call, $0) and a passcode-gated live run | https://leakproof-dashboard.onrender.com |
| Potential impact | of 78 patches that silenced the sanitizer on real OSS-Fuzz bugs, 21 (27%) were not fixes; the gate caught 17 of those 21, review found the other 4. On bugs opened in October 2026: a correct gpac fix and a partial assimp fix, packaged; silencers refused by quickjs's tests and by re-fuzzing | docs/NUMBERS.md ("Sanitizer silent is not fixed"); docs/REAL_WORLD.md |
| Quality of the idea | "verified fixes, or nothing": workers never see the gate; it re-fuzzes with amplified inputs and checks leaks and behaviour; calibrated on the developers' own fixes (accepts 24 of 27) | README "The evidence gate" |

**Limits up front:** the gate shows the crash is gone and no new sanitizer report appears on the inputs it tries, not that a fix is correct for every input, so every fix goes to a human before it is sent. ARVO's developer fixes are public and may be in the models' training data; the still-open bugs are the clean test. Leak results come from synthetic Juliet cases.

## The 30-second version

**On real OSS-Fuzz bugs, a "crash is gone" check would ship 21 bad AI patches out of 78, and "crash gone + tests pass" still ships 10 of the 49 that had tests. Leakproof ships 4 (3).** (Counted from the run records: [NUMBERS](https://github.com/samsundar989/nebius-hackathon/blob/main/docs/NUMBERS.md#sanitizer-silent-is-not-fixed).)

**A patch that passed the tests, refused.** For a real jq bug (OSS-Fuzz 42530604), the model's patch passed jq's own test suite and the original crash input ran clean. Leakproof doubled one number in that input, and the patched jq overflowed a heap buffer. The unpatched program and the developer's real fix are both clean on that input, so the patch was refused.

**Proof:** 15 of 27 real OSS-Fuzz bugs verified · 14 of them correct against the developers' own fixes · the gate accepts 24 of 27 developer fixes, so it is strict without being impossible.

**On bugs that are still open:** toybox #572 — a one-line fix, verified and passing toybox's 13 `patch` tests, packaged for a maintainer and not sent: a person decides.

---

## Who it's for

Maintainers and security teams with a backlog of OSS-Fuzz or sanitizer reports in C and C++, and CUDA teams whose kernels compute-sanitizer flags. They want patches they can review quickly, with the evidence attached.

## Inspiration

Fuzzers find memory bugs faster than maintainers can fix them, and LLMs now write patches for them. The catch: most "fixes" just make the crash go away. They clamp a bound, skip a code path or allocate one more byte, and a repair loop that stops at "the sanitizer is quiet" reports them as wins. Published work finds that checking only the original crash input inflates repair agents' solve rates by about 1.8× (PatchBench). We wanted an agent whose "fixed" you can believe, and whose "not fixed" tells you why.

## What it does

Given a sanitizer finding (a crash input plus a build), Leakproof:

1. builds and reproduces the bug in a sandbox;
2. has **Nemotron 3 Ultra** find the root cause and propose up to four fix hypotheses;
3. has four **Nemotron 3.5 Lightning** workers each write a patch on its own branch of the baseline checkpoint;
4. runs every candidate through an **evidence gate** in a separate process with the network off. A candidate passes only if it rebuilds, actually compiles into the binary, no longer crashes, passes the project's tests, behaves the same on a corpus, survives amplified and fuzzed inputs that the developer's real fix survives, and adds no leak or use-after-free;
5. on projects without tests or a fuzz harness (by default; opt-in elsewhere), has **Nemotron 3 Super** attack each candidate that passed every other check: it reads that one diff and writes up to 8 inputs meant to break it; each input runs on the patched and unpatched builds, and only a sanitizer report or an output difference rejects (Ultra steps in once if Super gives no usable input);
6. when several candidates verify, lets Ultra pick the one that best preserves the code's intent;
7. writes an evidence bundle for each case: the diff, every check with its evidence, and the cost.

**Which model does what:** Nemotron 3 Ultra plans (and picks between verified fixes), Nemotron 3.5 Lightning writes patches, Nemotron 3 Super attacks them, Nemotron 3 Nano reads issue reports for `leakproof init`.

It works on your own project through a short `leakproof.toml` (`leakproof init` drafts one, `leakproof fix` runs), triages piles of crash reports (`leakproof batch`), turns a verified fix into a ready-to-send patch (`leakproof package`), and ships a GitHub Action. Details: README and docs/NUMBERS.md.

## Results (real numbers, failed runs included)

- **Bugs opened in October 2026, after the models' training data** ([real world](https://github.com/samsundar989/nebius-hackathon/blob/main/docs/REAL_WORLD.md)). On 8 still-open sanitizer issues in assimp, gpac, quickjs-ng, json-c and LibreDWG (1.6k–13k★): 3 turned out to be fixed upstream already; of the 5 attempted, the gate verified 2. **gpac #4006: a correct 2-line fix** (hand-reviewed, packaged; it still needs the regression test gpac asks for). assimp #6927: verified, but partial on review, and said so. quickjs-ng #1853: three patches only silenced the crash; one even passed all of quickjs's own tests and was refused by re-fuzzing. Nothing sent; $1.08 in total.
- **27 real OSS-Fuzz bugs (ARVO, 13 projects):** the crash went away in 18. **15 verified** at $0.070 of model spend per verified fix. Compared by hand with the developers' own fixes, the chosen fix is correct in **14**.
- **Bugs that are still open upstream:** 40 open GitHub issues with sanitizer reports (three rounds) → 11 still reproduce at upstream HEAD with no fix PR → 7 verified by the gate → after review, 1 complete fix ready to propose (toybox #572, which also passes toybox's 13 `patch` tests) and 2 partial fixes (elk #82, utf8.h #1), each packaged for a maintainer; a human decides whether to send them, nothing was posted. Without tests or an output-printing harness the gate sees little, and most verified diffs were defensive or incomplete on review. Of the five wrong-or-incomplete findings that review made, two are now caught by a machine check:

  | case | review said | caught by |
  |---|---|---|
  | toybox #571 | the overflow recurs on other strings | inputs generated from the PoC |
  | toybox #572 (2 patches) | wrong: depends on the byte after the terminator | adversary inputs (Ultra: `\n--- "\"`) |
  | berry #544 | defensive; the undefined behaviour stays | still missed |
  | jsmn #249 | needs one more guard | still missed |
  | cNBT #28 | out-of-memory path still dereferences NULL | inconclusive |

  The ARVO numbers above come from the gate before the adversary existed. Calibrated on them afterwards, the adversary rejected none of the 24 developer fixes, every correct winner it reached (12 of 14) stayed verified, and it rejected none of the correct open-bug fixes.

- **The gate isn't just strict:** it accepts 24 of 27 of the developers' own fixes. One rejection is correct (that upstream fix leaks).
- **Gate precision:** 52 of 67 verified patches (78%) are correct when compared with the developer's fix. We publish the 8 that are wrong and explain how each fooled the gate.
- **The planner matters on real code:** same Lightning workers, 10 cases. No planner: 2 verified; Super: 4; Ultra: 7. Ultra was also cheaper per verified fix, because failed attempts cost money too.
- **Juliet CWE-401 (synthetic):** 94/100, every reproducible case, at $0.011 per fix.
- **CUDA (compute-sanitizer on a T4):** 3/3 verified. Two candidate patches silenced the sanitizer but printed the wrong answer; the gate rejected them.

## How we built it

Python 3.12 with the plain `openai` SDK against Nebius Token Factory. There's no agent framework: the loop is planner → workers → gate. Every model call is metered into a cost ledger with a hard budget stop, and the ledger matched the Token Factory billing page to within a cent. The gate runs on local Docker or on **Nebius Sandboxes** with `networking.enabled=false`. We wrote a small REST runner because the SDK has no networking switch. Workers branch from one saved checkpoint. A unit test fails if any worker-side module imports gate code, so workers can never see the tests, the corpus or the developer's fix. ARVO supplies reproducible OSS-Fuzz bugs; we calibrate the gate by running the developers' own fix commits through it.

## Challenges we ran into

Our own gate lied to us, seven different ways: it "verified" binaries the patch never compiled into; its fuzzer silently never ran; a slow input counted as a crash; the model could edit the fuzz harness; OSS-Fuzz build scripts can't run twice; line numbers moved under a pre-existing bug; and a fuzz harness can only see what it prints (two mosquitto patches passed every check yet pointed the config at the wrong listener). Each is in the README's "How a gate lies". Each fix was re-calibrated against the developers' own patches.

**A caveat we owe you:** ARVO's developer fixes have been public for years, so the models may have seen them during training. The still-open bugs, where no fix exists anywhere, are the clean test: 40 issues → 11 reproduce → 7 verified → 1 complete and 2 partial fixes ready after review; none sent yet.

## Accomplishments that we're proud of

Honest numbers: raw versus verified versus correct, side by side, regenerated from run records by scripts. The 8 wrong-but-verified patches we found are published, not hidden.

## What we learned

"The crash is gone" is cheap, and "correct" is expensive to prove. Enlarging the input (×2, ×8, ×64 digit runs) catches a surprising share of fake fixes. On real code a strong planner pays for itself. Thinking-off modes save tokens but give wrong answers on reasoning tasks.

## What's next

More real tests in the gate. jq, mosquitto (about 210 CUnit tests, after installing CUnit while preparing the baseline), libexif and libplist now run their own suites; the other projects' suites need dependencies their OSS-Fuzz images lack. Show reviewers where the evidence is thin: a verified fix whose project has no tests and whose fuzz harness prints nothing to compare is labelled "verified, needs human review". Run the GitHub Action on a real repository. Move ARVO to Sandboxes once its image importer handles symlinked layers.

## Built with

nvidia-nemotron, nemotron-3-ultra, nemotron-3.5-lightning, nemotron-3-super, nemotron-3-nano, nebius-token-factory, nebius-sandboxes, python, docker, addresssanitizer, leaksanitizer, libfuzzer, oss-fuzz, arvo, compute-sanitizer, cuda, kaggle, render, github-actions

## Feedback for Nebius and NVIDIA (short form; full version in docs/FEEDBACK.md)

- **Token Factory:** truly OpenAI-compatible; rate limits (600 RPM) are far above folklore; thinking control works through `chat_template_kwargs`. Needs work: `json_schema` numeric fields can decode digit by digit until `max_tokens`; `reasoning_effort` levels are ignored except on Super; the Batch API returned "temporarily unavailable"; there's no cost field in responses.
- **Sandboxes:** the checkpoint-and-branch model fits "baseline → N candidates → gate" exactly, and `networking.enabled=false` is honoured. Needs work: the SDK lacks the networking field; "not approved" returns 200 with all permissions false; the importer fails on older images with `NotImplementedError: chmod: follow_symlinks unavailable on this platform`; two different "project id" formats.
- **Nemotron:** Ultra is a strong planner and a useful first-pass reviewer (we overrode 8 of its 67 judgments). Lightning is a fast, cheap patch worker when its thinking budget is bounded. Super is a cheap adversary ($0.004 a call) but with thinking on it spent a 32k-token budget reasoning and returned nothing, and with thinking off it gave no usable JSON on about a third of calls.
- **compute-sanitizer:** exact reports, but the exit code is 0 on errors unless `--error-exitcode` is set, and it cannot attach under WSL2 yet prints a clean-looking report.

## Gallery images (rendered by `docs/devpost/render_assets.py`, 3:2 at 2×)

- Thumbnail: `docs/devpost/thumbnail.png` ("15/27 real bugs verified · 14 correct").
1. `docs/devpost/1_first_screen.png` — the dashboard's first screen (1440 px).
2. `docs/devpost/2_jq_refusal.png` — what a refusal looks like (jq).
3. `docs/devpost/3_head_to_head.png` — the 78 patches that silenced a real OSS-Fuzz crash, and the head-to-head: "crash is gone" ships 21 bad ones, Leakproof 4; with the project's tests (49), 10 vs 3.
4. `docs/devpost/4_planner.png` — how it works: which model does what, and the planner bars (2 → 4 → 7 of 10).
5. `docs/devpost/5_gate_matrix.png` — every check, every candidate (jq 42531297: one candidate verified, two refused because re-fuzzing the amplified PoC found a new crash).
6. `docs/devpost/6_review_findings.png` — wrong fixes a human review found on open bugs, and which machine check now catches them (2 of 5: generated inputs and the adversary; D-0078, D-0079).
7. `docs/devpost/7_phone_390.png` — the dashboard on a phone (390 px).
- Architecture: `docs/devpost/architecture.png`.
