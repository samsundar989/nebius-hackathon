# Video script v3 (2 min 54 s, matches `video/record.py` v5)

Screen + voice. The silent draft `video/leakproof_draft.mp4` follows this table scene by scene (captions burned in); read the "say" column over it.
Numbers are from `docs/NUMBERS.md`, `docs/REAL_WORLD.md` and the dashboard (generated from the same run records).
**The video must show the app working and say aloud how Nebius and NVIDIA are used** (organizer checklist): the sentences in bold below do that; keep them.

| time | on screen | say |
|---|---|---|
| 0:00–0:03 | title card | Leakproof. Verified fixes, or nothing. |
| 0:03–0:15 | jq evidence bundle | This patch for a real jq bug passed jq's own test suite, and the original crash input no longer crashes. Most repair tools would ship it. |
| 0:15–0:30 | dashboard refusal card | Leakproof doubled one number in that input, and the patched jq overflowed a heap buffer. The unpatched program and the developer's real fix are both clean on that input, so the patch was refused. |
| 0:30–0:40 | csvsplit crash under AddressSanitizer | Here's a bug to fix: a CSV splitter writes one byte past a buffer. |
| 0:40–0:56 | `leakproof fix`: plan, four workers, verdict | **Nemotron 3 Ultra, on Nebius Token Factory, finds the root cause and plans. Four Nemotron 3.5 Lightning workers each patch their own copy.** Then the gate, network off, rebuilds, re-runs the crash, runs the tests and re-fuzzes. |
| 0:56–1:07 | the winning diff | Verified: one byte more for the terminator. About a cent. |
| 1:07–1:21 | dashboard funnel | On 27 real OSS-Fuzz bugs the crash went away 18 times; 15 survived the gate. Of 78 patches that silenced the sanitizer, 21 were not fixes, and the gate caught 17. |
| 1:21–1:31 | calibration card | And the gate is not just strict: it accepts 24 of 27 of the developers' own fixes. |
| 1:31–1:45 | planner card | Which model does what? On real bugs, Ultra's plan takes the same Lightning workers from 2 to 7 verified fixes out of 10. |
| 1:45–1:58 | dashboard: Re-verify without AI on a stored patch | Don't take our word for it: this button re-runs the whole gate on a stored patch, no model call. This one "fixed" a use-after-free by deleting the free: rejected again, as a new leak. |
| 1:58–2:12 | dashboard CUDA panel | The same on the GPU: two patches made NVIDIA's compute-sanitizer go quiet, and both printed the wrong answer. Rejected. |
| 2:12–2:32 | mosquitto: "Other verified candidates (2): both wrong" | Where it falls short: two mosquitto patches passed every check yet pointed the config at the wrong listener. Our review caught them, so we report "verified and correct" next to "verified". |
| 2:32–2:48 | dashboard Real-world table | Bugs opened this month, after the models' training data: quickjs's own tests caught two patches that only silenced the crash; one assimp fix verified, partial on review, and we say so. |
| 2:48–2:54 | end card (dashboard link) | **Nemotron Ultra, Lightning, Super and Nano on Nebius Token Factory; the gate on Nebius Sandboxes.** Leakproof: verified fixes, or nothing. |

Accuracy notes for the narration (do not drop when shortening):
- The Re-verify scene replays a real response captured from the Render demo service (`video/reverify_render.json`: CWE416 …long_08, rejected then and now as a new leak, 29 s, 0 model calls); the caption says "(recorded)". To show it live instead, click it on https://leakproof-dashboard.onrender.com (wake the free instance first).
- Real world: assimp #6927 verified and hand-reviewed as partial (QUESTION 0022, not sent); quickjs-ng #1853's two built candidates were `silenced_only` (quickjs's tests failed); json-c #995's PoC misuses the API. Three shortlisted issues were already fixed upstream. Say "partial", never "fixed".
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
