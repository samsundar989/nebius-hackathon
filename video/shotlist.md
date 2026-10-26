# Video draft v4: shot list

`video/leakproof_draft.mp4` — 2:50, 1920×1080, silent, captions burned in (40 px in a band along the bottom 150 px that nothing else uses; also `captions.srt`). It follows `docs/VIDEO_SCRIPT.md` v2. Record your voice over it, or upload it with `captions.srt` if time is short. Rebuild with:

```
uv run python video/build_transcripts.py      # terminal transcripts from recorded runs
.venv-win/Scripts/python.exe video/record.py   # Playwright recordings + ffmpeg assembly
```

Readable at 1080p and on a phone: terminal scenes use a 28 px font, at most 19 lines, top-anchored above the caption band, with the result line boxed; lines appear at a steady pace so no terminal scene sits still for more than ~4 s. The fix is two scenes: plan → workers → verdict (Ultra's plan wrapped to 3 lines stays on screen through the verdict), then the winning diff with removed/added lines highlighted. Dashboard cards are isolated and zoomed to fill the frame above the caption band (funnel, planner and CUDA at 70–85 % of the frame height). Calibration is a summary card, not the per-case table.

| # | time | scene | on screen | source |
|---|---|---|---|---|
| 0 | 0:00–0:03 | title card | "Leakproof — Verified fixes, or nothing." · Nemotron on Nebius Token Factory · gate on Nebius Sandboxes | `video/card.html` |
| 1 | 0:03–0:15 | jq bundle | terminal: the refused jq patch's evidence bundle | `docs/bundles/42530604.md` |
| 2 | 0:15–0:30 | refusal card | the refused diff and the verified one-line fix | dashboard |
| 3 | 0:30–0:40 | csvsplit crash | terminal: the AddressSanitizer report | replay of `runs/demo_fix` |
| 4 | 0:40–0:56 | `leakproof fix` | terminal: Ultra's plan, 4 workers, verdict, evidence label | replay of `runs/demo_fix` |
| 5 | 0:56–1:07 | winning diff | terminal: `malloc(inner)` → `malloc(inner + 1)`, highlighted | replay of `runs/demo_fix` |
| 6 | 1:07–1:21 | funnel | crash gone 18 → verified 15 → correct 14 of 27 | dashboard |
| 7 | 1:21–1:31 | calibration | 24/27 developers' fixes accepted; 1 correct reject (mosquitto leak), 2 false rejects (libzip, quickjs) | `video/card.html?type=calibration` |
| 8 | 1:31–1:45 | planner card | no planner 2 → Super 4 → Ultra 7 of 10 | dashboard |
| 9 | 1:45–1:56 | `leakproof batch` | terminal: 10 inputs → 1 cluster → all clean | replay of `runs/demo_batch` |
| 10 | 1:56–2:10 | CUDA panel | two `silenced_only` candidates | dashboard |
| 11 | 2:10–2:30 | mosquitto | "Other verified candidates (2): both wrong", expanded | dashboard |
| 12 | 2:30–2:44 | open bugs | 30 open GitHub issues → 7 reproduce without a fix PR → 5 verified → 1 ready (toybox #572, one line, 13/13 of toybox's tests); the review-finding table with the "caught by" column (generated inputs, adversary inputs, still missed) | `video/card.html?type=openbugs` (reads `cases/open_bugs/REVIEW.md`) |
| 13 | 2:44–2:50 | end card | 15/27 · 14/27 · 24/27 · 2 → 7 (104 px numbers, 34 px labels); repo link (the dashboard link goes in when Render or Pages is live) | `video/card.html` |

Notes:
- The terminal scenes are replays of recorded runs, rebuilt from their run records (each starts with a `# replay of a recorded run` line); no new model calls. Narrate them as "a recorded run", or re-record steps 2–4 of `scripts/demo_run.sh` live if you prefer.
- Captions condense the narration; the full spoken text is the "say" column of `docs/VIDEO_SCRIPT.md` (scene times above supersede the script's).
- Say aloud: "Nemotron 3 Ultra and 3.5 Lightning on Nebius Token Factory" (scene 4) and "the gate runs on Nebius Sandboxes with networking off" (scene 11; see the script's accuracy notes for the exact phrasing).
- The end card says "(link when deployed)" for the dashboard until Render or Pages is live; rebuild then.
