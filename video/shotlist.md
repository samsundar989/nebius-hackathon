# Video draft v6: shot list

`video/leakproof_draft.mp4` — 2:10, 1920×1080, silent, captions burned in (40 px in a band along the bottom 150 px that nothing else uses; also `captions.srt`). It follows `docs/VIDEO_SCRIPT.md` v4 and is recorded from the new dashboard (review #22). Record your voice over it, or upload it with `captions.srt` if time is short. Rebuild with:

```
uv run python video/build_transcripts.py      # terminal transcripts from recorded runs
.venv-win/Scripts/python.exe video/record.py   # Playwright recordings + ffmpeg assembly
```

Dashboard sections are isolated and zoomed to fill the frame above the caption band; a section taller than the frame pans slowly.

| # | time | scene | on screen | source |
|---|---|---|---|---|
| 0 | 0:00–0:03 | title card | "Leakproof — Verified fixes, or nothing." | `video/card.html` |
| 1 | 0:03–0:11 | hero | "1 in 4 AI patches that make a crash go away isn't a fix." and the one-line summary | dashboard hero |
| 2 | 0:11–0:29 | waffle + head-to-head | 78 patches (53 correct, 4 defensive, 4 wrong but shipped, 17 refused); "crash is gone" 21 vs Leakproof 4; tests ran (49): 10 vs 3 | dashboard, computed from the run records |
| 3 | 0:29–0:43 | re-check a stored patch | the buttons and the re-check result: a patch that deleted a `free`, `rejected:new_leak` now and then, 0 model calls (a real Render response, replayed; captioned "recorded") | dashboard + `video/reverify_render.json` |
| 4 | 0:43–0:59 | how it works | five steps with the model roles, planner bars 2 → 4 → 7 of 10 | dashboard |
| 5 | 0:59–1:13 | `leakproof fix` | terminal: Ultra's plan, 4 workers, verdict (a replay of a recorded run) | replay of `runs/demo_fix` |
| 6 | 1:13–1:28 | refusal | the refused jq diff and the verified one-line fix | dashboard |
| 7 | 1:28–1:41 | new bugs | October 2026 issues, gpac #4006 first (fixed upstream Oct 29 at the same line, same result; shortlisted issues already fixed before we started are hidden) | dashboard |
| 8 | 1:41–1:55 | explorer | jq 42531297: every candidate, every check | dashboard |
| 9 | 1:55–2:04 | limits | the five limits | dashboard |
| 10 | 2:04–2:10 | end card | headline numbers; repo and dashboard links | `video/card.html` |

Notes:
- The terminal scene is a replay of a recorded run, rebuilt from its run record (it starts with a `# replay of a recorded run` line); no new model calls. Say "a recorded run".
- Captions condense the narration; the full spoken text is the "say" column of `docs/VIDEO_SCRIPT.md`.
- Say aloud the bold sentences (Nebius Token Factory, the four Nemotron models, Nebius Sandboxes).
- "Reviewed" means reviewed by Claude outside the pipeline (D-0081); "a person decides what is sent" means Samuel.
