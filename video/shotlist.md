# Video draft v2: shot list

`video/leakproof_draft.mp4` — 2:49, 1920×1080, silent, captions burned in (40 px on a dark band; also `captions.srt`). It follows `docs/VIDEO_SCRIPT.md` v2. Record your voice over it, or upload it with `captions.srt` if time is short. Rebuild with:

```
uv run python video/build_transcripts.py      # terminal transcripts from recorded runs
.venv-win/Scripts/python.exe video/record.py   # Playwright recordings + ffmpeg assembly
```

Readable at 1080p and on a phone: terminal scenes use a 28 px font with at most 22 lines, and the result line is boxed. Each dashboard scene shows one card, zoomed to fill the frame, and pans slowly when the card is taller than the screen.

| # | time | scene | on screen | source |
|---|---|---|---|---|
| 0 | 0:00–0:03 | title card | "Leakproof — Verified fixes, or nothing." · Nemotron on Nebius Token Factory · gate on Nebius Sandboxes | `video/card.html` |
| 1 | 0:03–0:15 | jq bundle | terminal: the refused jq patch's evidence bundle | `docs/bundles/42530604.md` |
| 2 | 0:15–0:30 | refusal card | the refused diff and the verified one-line fix | dashboard |
| 3 | 0:30–0:42 | csvsplit crash | terminal: the AddressSanitizer report | replay of `runs/demo_fix` |
| 4 | 0:42–1:14 | `leakproof fix` | terminal: plan, 4 workers, verdict, evidence label, winning diff | replay of `runs/demo_fix` |
| 5 | 1:14–1:30 | funnel | crash gone 18 → verified 15 → correct 14 of 27 | dashboard |
| 6 | 1:30–1:42 | calibration | the developers' own fixes: 24 of 27 accepted | dashboard |
| 7 | 1:42–1:57 | planner card | no planner 2 → Super 4 → Ultra 7 of 10 | dashboard |
| 8 | 1:57–2:10 | `leakproof batch` | terminal: 10 inputs → 1 cluster → all clean | replay of `runs/demo_batch` |
| 9 | 2:10–2:24 | CUDA panel | two `silenced_only` candidates | dashboard |
| 10 | 2:24–2:44 | mosquitto | "Other verified candidates (2): both wrong", expanded | dashboard |
| 11 | 2:44–2:49 | end card | 15/27 · 14/27 · 24/27 · 2 → 7; repo and dashboard links | `video/card.html` |

Notes:
- The terminal scenes are replays of recorded runs, rebuilt from their run records (each starts with a `# replay of a recorded run` line); no new model calls. Narrate them as "a recorded run", or re-record steps 2–4 of `scripts/demo_run.sh` live if you prefer.
- Captions condense the narration; the full spoken text is the "say" column of `docs/VIDEO_SCRIPT.md` (scene times above supersede the script's).
- Say aloud: "Nemotron 3 Ultra and 3.5 Lightning on Nebius Token Factory" (scene 4) and "the gate runs on Nebius Sandboxes with networking off" (scene 10; see the script's accuracy notes for the exact phrasing).
- The end card says "(link when deployed)" for the dashboard until Render or Pages is live; rebuild then.
