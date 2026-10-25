# Video draft: shot list

`video/leakproof_draft.mp4` (2:55, 1440×900, silent, captions burned in) follows `docs/VIDEO_SCRIPT.md` v2. Record your voice over it, or upload it with `captions.srt` if time is short. Rebuild everything with:

```
uv run python video/build_transcripts.py      # terminal transcripts from recorded runs
.venv-win/Scripts/python.exe video/record.py   # Playwright recordings + ffmpeg assembly
```

| # | time | scene | what is on screen | source |
|---|---|---|---|---|
| 1 | 0:00–0:15 | jq bundle | terminal: the evidence bundle of the refused jq patch | `runs/p3_arvo27_r1`, `docs/bundles/42530604.md` |
| 2 | 0:15–0:30 | refusal card | dashboard: refused diff and the verified one-line fix | `site/` (`numbers.json`) |
| 3 | 0:30–0:45 | csvsplit crash | terminal: the AddressSanitizer report | replay of `runs/demo_fix` |
| 4 | 0:45–1:20 | `leakproof fix` | terminal: plan, 4 workers, verdict, evidence label, winning diff | replay of `runs/demo_fix` |
| 5 | 1:20–1:50 | first screen → funnel → calibration | dashboard: headline numbers, the funnel bars, calibration counts | `site/` |
| 6 | 1:50–2:05 | planner card | dashboard: 2 → 4 → 7 of 10 | `site/` |
| 7 | 2:05–2:20 | `leakproof batch` | terminal: 10 inputs → 1 cluster → all clean | replay of `runs/demo_batch` |
| 8 | 2:20–2:35 | CUDA panel | dashboard: the two `silenced_only` candidates | `site/` |
| 9 | 2:35–2:55 | mosquitto case page | dashboard: "Other verified candidates (2): both wrong" opened | `site/` |

Notes:
- The terminal scenes are replays of recorded runs, rebuilt from their run records (each starts with a `# replay of a recorded run` line); no new model calls. Narrate them as "a recorded run" or re-record steps 2–4 of `scripts/demo_run.sh` live if you prefer.
- Captions condense the narration; the full spoken text is the "say" column of `docs/VIDEO_SCRIPT.md`.
- Say aloud: "Nemotron 3 Ultra and 3.5 Lightning on Nebius Token Factory" (scene 4) and "the gate runs on Nebius Sandboxes with networking off" (scene 9; the accuracy notes in the script say how to phrase it).
