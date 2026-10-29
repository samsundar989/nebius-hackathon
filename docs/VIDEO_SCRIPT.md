# Video script v4 (2 min 10 s, matches `video/record.py` v6, recorded from the new dashboard)

Screen + voice. The silent draft `video/leakproof_draft.mp4` follows this table scene by scene (captions burned in); read the "say" column over it. There is room to speak slowly: the cut is 2:10 and the limit is 2:55.
Numbers are from `docs/NUMBERS.md`, `docs/REAL_WORLD.md` and the dashboard (generated from the same run records).
**The video must show the app working and say aloud how Nebius and NVIDIA are used** (organizer checklist): the sentences in bold below do that; keep them.

| time | on screen | say |
|---|---|---|
| 0:00–0:03 | title card | Leakproof. Verified fixes, or nothing. |
| 0:03–0:11 | hero sentence | One in four AI patches that make a crash go away isn't a fix. Leakproof fixes memory bugs in C, C++ and CUDA, then tries to break every patch, and ships only the ones that survive. |
| 0:11–0:29 | the waffle of 78 patches and the head-to-head (hold) | These are 78 patches from Nemotron workers that made a real OSS-Fuzz crash disappear. Green is a correct fix; the red ones are not fixes. A "crash is gone" check would ship all 21 bad ones. Leakproof ships 4. Even where the project's own tests ran, "crash gone and tests pass" ships 10 bad patches out of 49; Leakproof ships 3. |
| 0:29–0:43 | "Re-check a stored patch" on the dashboard | Don't take our word for it: this button re-runs the whole gate on a stored patch, with no model call and no cost. This patch "fixed" a use-after-free by deleting the free; it's rejected again, as a new leak. |
| 0:43–0:59 | How it works: five steps with model roles, planner bars | **Four NVIDIA Nemotron models on Nebius Token Factory: Nemotron 3 Ultra finds the root cause and plans; four Nemotron 3.5 Lightning workers each patch their own copy; Super writes inputs to break a patch; Nano drafts the config from a bug report.** With Ultra's plan, the same workers go from 2 to 7 verified fixes out of 10. |
| 0:59–1:13 | terminal: `leakproof fix` on the CSV splitter | A recorded run on a small bug: plan, four workers, then the gate, network off: rebuild, re-run the crash, run the tests, re-fuzz. Verified, for about a cent. **The gate also runs on Nebius Sandboxes.** |
| 1:13–1:28 | What a refusal looks like (jq) | This jq patch passed jq's own test suite. Leakproof doubled one number in the crash input, and the patched jq overflowed. The developer's real fix is clean on that input, so the patch was refused. |
| 1:28–1:41 | New bugs, October 2026 | Bugs reported this month, after the models' training data, so there was no fix to copy. Leakproof's two-line gpac fix passed gpac's own tests; hours later, gpac's maintainer fixed the same line, with the same result. A person decides what is sent. |
| 1:41–1:55 | Every run, every check (explorer) | Every run and every check is here, with its evidence: hover a check to see why it passed or failed. |
| 1:55–2:04 | Limits | "Verified" means safe on every input we tried, not proven correct. That's why we also report "verified and correct", and why a person reviews every fix before it's sent. |
| 2:04–2:10 | end card (dashboard link) | **Nemotron Ultra, Lightning, Super and Nano on Nebius Token Factory.** Leakproof: verified fixes, or nothing. |

Accuracy notes for the narration (do not drop when shortening):
- The re-check scene replays a real response captured from the Render demo service (`video/reverify_render.json`: CWE416 …long_08, rejected then and now as a new leak, 29 s, 0 model calls); the caption says "(recorded)". To show it live instead, click it on https://leakproof-dashboard.onrender.com (wake the free instance first).
- Who reviewed: the "correct / wrong / partial" reviews were done by Claude (Claude Code and the strategist), outside the pipeline, not by Samuel (D-0081). Do not say "we reviewed by hand". "A person decides what is sent" is true: Samuel.
- Real world: gpac #4006 verified and reviewed as correct (by Claude, outside the pipeline); its regression test fails under ASan before the fix and passes after; gpac shipped an equivalent fix on Oct 29 (3f05654) before ours was sent (QUESTION 0023: not sending); assimp #6927 verified and reviewed as partial (QUESTION 0022, not sent); quickjs-ng #1853: three silencers refused over two runs (two failed quickjs's tests; one passed them and re-fuzzing hit the same overflow); json-c #995's PoC misuses the API. Three shortlisted issues were already fixed upstream. Say "partial", never "fixed".
- Super attacks verified candidates on projects without tests (the adversary); Nano drafts configs from bug reports (`leakproof init --issue-text`).
- The jq refusal is P3 run 1, case 42530604 (worker H2·w1); the verified one-line fix (`digits + 20`) is from run 2.
- Say "on Nebius Sandboxes" only about the gate in general: the Juliet runs and a bring-your-own run (csvsplit, `--runner sandboxes`) used Sandboxes; ARVO images do not import there yet, so ARVO ran on local Docker, and the recorded terminal scenes are local Docker runs (README).
- The planner comparison is one repeat on 10 cases (2/4/7 verified; verified and correct 2/3/5, from `site/data/numbers.json`).

B-roll to capture (dashboard served locally or on Render, 1440×900):
1. The first screen: five headline numbers, the jq refusal card, the planner card.
2. A gate matrix: mosquitto 42520955's case page, with "Other verified candidates (2): both wrong" open and the evidence badge visible.
3. The calibration counts table (24 of 27 developer fixes accepted).
4. The planner card close up (2 → 4 → 7 of 10).
5. `docs/architecture.svg`.
6. The terminal at the end of `leakproof batch` ("1/1 clusters verified for every member input").

Recording notes: run `scripts/demo_run.sh` once beforehand so images are pulled; keep the terminal at 110 columns; the dashboard is the Render static site (or `site/` served locally: `cd site && python -m http.server 8765`). Do not show `.env` or the Render environment page.
