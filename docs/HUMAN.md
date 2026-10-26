# HUMAN — questions for Samuel and his answers

Builder (Claude Code) appends `## QUESTION NNNN` blocks. Samuel answers with `## ANSWER NNNN` blocks. Builder takes a sensible default and continues unless the question is about money, licensing, or something irreversible.

## QUESTION 0001 — AI Cloud billing status (needed before kickoff step 3.7)
Has the Nebius AI Cloud card been added and the $25 top-up landed as balance? Do the eu-north1 quotas show L40S > 0 and preemptible VMs > 0? (Console → Administration → Limits → Quotas.) Reply with ANSWER 0001.

## QUESTION 0002 — Sandboxes beta
Has the Sandboxes beta request been approved (does `GET /sandboxes/v1/whoami` return 200)? If still 403 after 24 h, please post in the Nebius Discord Sandboxes channel and email contree@nebius.com mentioning the Devpost hackathon. Reply with ANSWER 0002 when it changes.

## QUESTION 0003 — C: drive is full; Docker's disk needs compacting (needs you, admin)
During E0, Docker Desktop's data disk (`C:\Users\<user>\AppData\Local\Docker\wsl\disk\docker_data.vhdx`) grew from 15.6 GB to 45.3 GB (CUDA image 11.5 GB, three ARVO images at ~5.3 GB each). C: is now at 100% (18 GB free). The machine crashed mid-session; I can't prove this was the cause, but a full system drive is a likely contributor. I have deleted the ARVO images and build cache (~29 GB freed *inside* the VHDX), but the VHDX is not sparse, so Windows gets nothing back until it is compacted. That needs `wsl --shutdown` (which kills every WSL session, including Claude Code) and an admin shell, so it's yours to run when convenient:
```powershell
# Admin PowerShell, with Docker Desktop quit and no WSL work you care about running
wsl --shutdown
Optimize-VHD -Path "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx" -Mode Full   # needs the Hyper-V PowerShell module
# no Hyper-V module? use diskpart:  select vdisk file="<path above>"  /  attach vdisk readonly  /  compact vdisk  /  detach vdisk
# optional, so future deletes return space automatically:
wsl --manage docker-desktop --set-sparse true
```
Longer term: move Docker's disk image location to a drive with room (Docker Desktop → Settings → Resources → Advanced → Disk image location). ARVO evals need ~5.5 GB per case while it runs. Until you answer, I pull at most one ARVO image at a time and delete it afterwards, and all container work goes through workerq. Reply ANSWER 0003.

## QUESTION 0004 — ARVO has no memory-leak cases
None of ARVO's 6,138 records is a leak, and its reproducer runs with `detect_leaks=0` (details: docs/ARVO_NOTES.md). The plan's "leak-led headline on ARVO" can't come from ARVO. Options: (a) ARVO headline = UAF/double free/overflows, leaks shown on Juliet plus real OSS-Fuzz "Memory leak" issues gathered by hand; (b) re-run ARVO harnesses with `detect_leaks=1` to harvest incidental leaks (untested, and those have no ground-truth fix); (c) both. **Default: (a)**, with (b) tried as a spike in E1 if time allows. Reply ANSWER 0004.

## QUESTION 0005 — Sandboxes: approval looks different from what we expected
`GET /sandboxes/v1/whoami` returns **200** (not 403), with every permission false (`spawn`, `import`, `list`, …). The ContreeRunner treats "spawn false" as not approved and its tests skip with that reason. When you chase approval, it may help to quote that response. Also, contree-sdk 0.3.6 has no per-run networking switch, so the offline gate can't run on Contree with that SDK version yet (FEEDBACK.md). No action needed beyond QUESTION 0002.

## QUESTION 0006 — compute-sanitizer on the local 5090 (optional, admin registry change)
compute-sanitizer can't attach to the RTX 5090 from WSL2/Docker: `Failed to initialize WDDM debugger interface. Please run EnableDebuggerInterface.bat as an administrator`. It also needs a CUDA ≥ 12.8 image for sm_120 (another ~12 GB pull). Enabling it means running NVIDIA's `EnableDebuggerInterface.bat` as admin, which changes a Windows registry setting for the GPU driver, so it's your call. **Default: leave the machine alone and run CUDA checks on Kaggle** (works now, 45 s per run, free; uses the same Kaggle GPU quota as your ARC project) or on the L40S once QUESTION 0001 is answered. Reply ANSWER 0006 only if you want local CUDA sanitizing.

## QUESTION 0007 — Kaggle GPU quota (CUDA extension)
Is ~1–2 h of Kaggle T4 time free this week for the three CUDA compute-sanitizer cases (Phase 3, Oct 26)? Default: assume yes, use ≤ 1 h.

## QUESTION 0008 — Render account for the demo button
The "run one Juliet case" button is a free Render web service (no card). Please create a Render account (https://render.com) and connect the GitHub repo, or say "skip" and the demo URL will be the GitHub Pages dashboard with recorded runs only. Default: build the service; deploy when you confirm.

## QUESTION 0009 — Video narration
Default: you record screen + voice on Oct 28 from `docs/VIDEO_SCRIPT.md` and `scripts/demo_run.sh`. Say if you want a captions-only video instead.

## NOTE 0010 — Sandboxes access is live (builder update, no answer needed)
2026-10-23: `GET /sandboxes/v1/whoami` with the Token Factory project id (`NEBIUS_PROJECT_ID`, `aiproject-…`) returns all permissions `true` (spawn, import, list, …). With the AI Cloud id (`NEBIUS_AI_PROJECT`, `project-…`) it still says all `false`. So QUESTION 0002/0005 are resolved on the platform side. Per kickoff §1 rule 2 I'll add the thin REST backend (networking off, ≤ 2 h, behind a flag) after the Phase 1 exit, not before. If `NEBIUS_AI_PROJECT` is meant to equal the Token Factory id (CLAUDE.md says "same value"), you may want to correct it in `.env`; I have not touched `.env`.

## ANSWER 0001 — AI Cloud
Skip Nebius AI Cloud (Serverless Jobs/Endpoints) for this submission. Sandboxes access is live and is the stronger Nebius story; CUDA stays on Kaggle. Do not create AI Cloud resources unless a later answer says otherwise. (Recorded by the strategist 2026-10-23 on Samuel's behalf; Samuel may override.)

## ANSWER 0002 / 0005 — Sandboxes
Resolved: access is live with the Token Factory project id (NOTE 0010).

## ANSWER 0003 — Disk
Resolved: C: has ~198 GB free. Keep the < 10 GB stop rule.

## ANSWER 0004 — Leaks
Option (a): ARVO headline = UAF/double free/overflows; leaks from Juliet (+ optional mined case studies). README states ARVO has no leak cases.

## ANSWER 0006 — Local CUDA
Leave the machine alone (no registry change). CUDA runs on Kaggle.

## ANSWER 0007 — Kaggle
1 hour of T4 time is available in total. Plan ≤ 30 min: batch all CUDA cases of a round into one kernel run; keep ≥ 30 min in reserve for re-runs and the video.

## ANSWER 0008 — Render
Samuel has a Render account. He will: connect the GitHub repo to Render now, create a dedicated Token Factory API key for the demo, and enable GitHub Pages (Source: GitHub Actions). He creates the Render service himself from `render.yaml` when you tell him it is ready (see KICKOFF_ADDENDUM_2026-10-23_PHASE2.md §6). Never put a key in the repo.

## ANSWER 0009 — Video
Samuel records screen + voice when `docs/VIDEO_SCRIPT.md` and `scripts/demo_run.sh` are ready (target Mon night or Tue Oct 28). Tell him in HUMAN.md the moment they are ready.

## ANSWER 0010 — .env
Fixed: `NEBIUS_AI_PROJECT` now equals `NEBIUS_PROJECT_ID` (Token Factory id).

## ANSWER 0008 (amended 2026-10-23 21:45) — hosting
The repo is private on GitHub Free, so GitHub Pages is unavailable. Do **not** use Pages. Both the dashboard (Render static site) and the live button (Render web service) come from one `render.yaml` Blueprint; see KICKOFF_ADDENDUM §6. Samuel has connected (or is connecting) the Render GitHub app to this repo and has a dedicated demo key ready.

## QUESTION 0012 — One-time history rewrite before going public (needs a yes/no)
2026-10-23: `docs/research/` and `docs/kickoff/` are now gitignored and untracked (files stay on disk), but they and some earlier wording are still in past commits, which become visible when the repo goes public on Oct 28. Removing them needs a one-time `git filter-repo` (drop both folders from every commit, plus `--replace-text` for the reworded lines) and **one force-push while the repo is still private**. CLAUDE.md forbids force-pushes, so I will not do it without your yes. This is irreversible for the old history; other checkouts (and Render's clone) must re-clone or hard-reset afterwards.
- **yes** → I do it Tue Oct 28 morning after the Mon rewording, then update commit hashes quoted in `docs/REPORT_SHIP.md`/`docs/DECISIONS.md` from filter-repo's commit map, re-run CI, and tell you to re-clone.
- **no** (default if unanswered) → no rewrite; the rewording of current files still happens Mon Oct 27.

## QUESTION 0013 — What does a Nebius Sandboxes run cost? (money; needs your look at billing)
2026-10-24: every Sandboxes run returns `resources.cost` (e.g. 0.0025 for a 2 s Juliet build, 0.086 for a 27 s apt install). We record it in `runs/cost_ledger.jsonl` as USD (`model: sandboxes`, `kind: compute`), which puts Sandboxes at **$3.23** of the ledger's $5.58 — 3× the model spend for the same Juliet cases. If that unit really is USD, Sandboxes costs ~$1–4/sandbox-hour, which seems high; I found no public pricing. **Please check the Token Factory billing page for Sandboxes charges on Oct 23–24** and reply with the amount (or "not billed"/"credits").
- Until you answer (default): no new Sandboxes batches; the leaderboard and the 22 re-runs go to local Docker via workerq. The ledger keeps counting Sandboxes cost as USD (conservative: it can only trip the cap early).
- If it is not USD / not billed: I re-label those entries and move Juliet back to Sandboxes (8–16× parallel, 41 s for 100 reproductions).

## ANSWER 0013 — Sandboxes cost: not billed
Checked by the strategist on Samuel's Token Factory billing page (Billing → Usage, "last updated 19:04 UTC" 2026-10-24, range Sep 24–Oct 24): the only line items are Nemotron token charges (Ultra in/out/cached, 3.5 Lightning in/out/cached, Nano, Super) — subtotal **$3.27** + VAT $0.22. **There is no Sandboxes line**, although our Sandboxes runs on Oct 23–24 happened hours before that update. Account balance $17.80. So: relabel the Sandboxes `cost` entries as unitless `sandbox_units` (not USD), exclude them from budget caps and $ totals, keep summing the units for FEEDBACK, and move Juliet batches back to Sandboxes. Bonus: the ledger's model spend ($3.28) matches Nebius billing ($3.27) within $0.01 — say so in the README cost section and in FEEDBACK.

## NOTE 0014 — Strategist channel (read every loop iteration)
From now on, strategist reviews and orders arrive in `docs/kickoff/STRATEGIST_NOTES.md` (gitignored, newest entry at the top). Read it at the start of every loop iteration, before choosing the next task; it amends the kickoff and the Phase 2 addendum. Acknowledge each new entry with one line in that day's REPORT_SHIP section ("Strategist notes <timestamp>: read, acting on …").

## QUESTION 0015 — P3 r2 budget: up to $3.00 for one batch (money)
2026-10-24: P3 r2 (27 ARVO cases with the edit fallbacks and one repair round, strategist order B4) is estimated at ~$2.2–2.8 model spend (r1 was $1.05; a repair round adds an Ultra re-plan with whole files plus 4 Lightning workers, ~$0.10 per unverified case). CLAUDE.md asks before any single action > $2. **Default while unanswered:** the batch runs with a hard cap of `--budget 1.95`; it is resumable, so cases it could not reach are listed as `not_run`. Reply "yes" and I resume the same run with `--budget 3.0`. Ledger model spend so far: $3.28 (Nebius billing $3.27); $25 cap.

## QUESTION 0011 — Render ready (please apply the Blueprint and send both URLs)
2026-10-24: `render.yaml`, `site/` and `service/` are on `main`. Local checks passed: `docker build` of the service; recorded-mode smoke; live-mode smoke **3/3 Juliet cases verified in 16–24 s, $0.005–0.012 each**, and the isolation probe confirmed that code running as `nobody` (how candidate code runs) cannot read the API key from the server's `/proc/1/environ` (D-0061).
Your clicks:
1. Render → **New → Blueprint** → repo `samsundar989/nebius-hackathon` (private, via the Render GitHub app) → it finds `render.yaml` with two services: `leakproof-dashboard` (static site) and `leakproof-demo` (free web service, Docker).
2. Paste the **demo** Token Factory key into `NEBIUS_API_KEY` and the project id into `NEBIUS_PROJECT_ID` (asked once, at creation) → **Apply**.
3. When both are deployed, copy the static-site URL and the web-service URL into `## ANSWER 0011`.
4. Live runs ship **off** (`DEMO_ENABLED=false`): the button serves labelled recorded results. When you want the live button, set `DEMO_ENABLED=true` on `leakproof-demo` → Environment (it redeploys). Caps: 25 runs/day, 3 per visitor per 10 min, $0.50 service budget (counters reset on restart); flipping it back to `false` is the kill switch.
After your answer I set `site/config.json` to the service URL, push, and test from a clean browser.

**Update 2026-10-25 (review #10 order 7):** a GitHub Pages fallback is ready: `.github/workflows/pages.yml` deploys `site/` and runs only when started by hand. Pages needs the repo public, so after Tuesday's visibility change: Settings → Pages → Source: "GitHub Actions", then Actions → pages → Run workflow. Default unchanged: if Render is not applied by Mon 12:00 CDT, I switch the README, DEVPOST and video end-card links to the Pages URL once it exists.
## NOTE 0016 — Video assets are ready to record (per ANSWER 0009)
2026-10-24: `docs/VIDEO_SCRIPT.md` (≈ 2:50, scene by scene: what is on screen and what to say) and `scripts/demo_run.sh` (4 steps, each waits for Enter; ~$0.03, ~6 min) are ready and were tested end to end through the queue: (1) the csvsplit heap overflow under AddressSanitizer, (2) `leakproof fix` → verified, one-line fix, (3) `leakproof batch` → 10 inputs, 1 cluster, all 6 crashing inputs clean, (4) the evidence bundle for the jq case the gate refused. Run it from Git Bash or WSL in the repo root with Docker running and the queue idle (it runs Docker directly). The dashboard shots need the Render static site (QUESTION 0011) or `cd site && python -m http.server 8765`. Numbers in the script are current; I will update them in place if the r2 batch finishes (QUESTION 0015) before you record.

**Update 2026-10-25 (v2, per strategist review #4):** the script now opens on the jq refusal (0:00–0:30), then the live csvsplit fix, the funnel with the new "verified and correct" tier (14/27) and calibration, the planner comparison (2 → 4 → 7 of 10), batch, CUDA, and the mosquitto limitation; it names Nemotron 3 Ultra / 3.5 Lightning on Nebius Token Factory and Nebius Sandboxes aloud. `scripts/demo_run.sh` steps follow the same order (jq bundle first). Same cost and runtime.

**Update 2026-10-25 (video draft, strategist review #6 order 2):** `video/leakproof_draft.mp4` (local file, not committed; rebuild with `.venv-win/Scripts/python.exe video/record.py`) is a 2:55 silent cut in script order at 1440×900, with captions burned in and also in `video/captions.srt`. `video/shotlist.md` lists the 9 scenes, their sources and what to say. The terminal scenes are replays of recorded runs (labelled as such on screen); the dashboard scenes are recorded from `site/`. You only need to record your voice over it, or upload it with the captions if short on time.

**Update 2026-10-25 (video v2, strategist review #7):** rebuilt to be readable at 1080p and on a phone: 1920×1080, terminal text at 28 px with the result line boxed, each dashboard scene shows one card filling the frame, a 3 s title card and a 5 s end card with the four headline numbers; 2:49 in total. `video/shotlist.md` has the new scene times.

**Update 2026-10-25 (video v3, strategist review #8 order 2): ready for narration.** `video/leakproof_draft.mp4` (local, not committed; rebuild as before) is 2:36: captions sit in a bottom band nothing else uses; terminal text starts at the top; the fix scene is split into plan → workers → verdict and then the winning diff with the changed lines highlighted; calibration is a summary card (24/27 accepted, 1 correct reject, 2 false rejects with one-line reasons); the funnel, planner and CUDA cards fill 70–85 % of the frame height; the end card numbers are 104 px. Scene times are in `video/shotlist.md` and supersede the script's. Frames were pulled and checked at every scene.

**Update 2026-10-25 (video v4, strategist review #9 order 2): v4 ready for narration.** 2:50. New 14 s scene after the mosquitto limitation: the open-bugs funnel (30 → 7 → 5 → 1 ready: toybox #572, one line, passes toybox's 13 tests) and the review-finding table, whose "caught by" column now shows the adversary catching both wrong #572 fixes. The end card no longer has the dashboard placeholder line. Scene times: `video/shotlist.md`.

**Update 2026-10-26 (review #11 order 4): the simplest way to record.** One continuous take while the silent video plays: open `video/leakproof_draft.mp4` on one screen and `docs/VIDEO_SCRIPT.md` (the "say" column; scene times in `video/shotlist.md`) on the other, start Windows Voice Recorder (or Audacity: File → Export → WAV), press play on the video and read along. Small timing slips are fine; keep the whole take under 2:59. Then `bash video/mux.sh path/to/narration.wav` normalises the loudness, mixes it onto the video and writes `video/leakproof_final.mp4`; it refuses anything over 2:59. Voice Recorder saves `.m4a`; mux.sh takes that too.

**Update 2026-10-26 (review #14 order 4): a fallback narration exists — use it only if you have not recorded by Tue 18:00 CDT.** `video/leakproof_tts.mp4` (local, not committed; rebuild with `.venv-win/Scripts/python.exe video/tts.py` then `bash video/mux.sh video/narration_tts.wav video/leakproof_tts.mp4`) speaks each caption at its time with the voice built into Windows (Microsoft Zira, offline; no download). Honestly: it is the legacy desktop voice and sounds clearly synthetic, nothing like a neural voice — your own voice, or the silent cut with its burned-in captions, is better. Piper (the open neural TTS the strategist suggested) needs a program and voice-model download, which I did not do without your OK. The draft and `leakproof_final.mp4` are untouched.

**Update 2026-10-26 (review #15 order 1): the fallback stays on the Windows voice.** The strategist allowed downloading Piper and one permissively licensed voice model, but downloading and running a program is something I only do on your OK in the chat, and you have not been reachable today. If you want the better voice, say so in chat (Piper plus one CC BY 4.0 / CC0 / MIT voice, ~60 MB), and I will build it and compare it with Zira. Otherwise: your own recording, or the silent cut with captions, then `video/leakproof_tts.mp4` only as a last resort. Also new: if you record and mix tonight, Tuesday's `set_links.py --dashboard … --rebuild-video` re-mixes your narration onto the new end card by itself.

## QUESTION 0017 — One fix for a still-open upstream bug is ready for your review (your decision; nothing has been posted)
2026-10-25, per strategist review #6 order 1. Leakproof ran on 14 open, public GitHub issues with sanitizer reports (`cases/open_bugs/TRIAGE.md`): 6 still reproduce at upstream HEAD, 4 have no open fix PR, 3 were verified by the gate, and after Ultra's review and mine **one** is ready to propose (`cases/open_bugs/REVIEW.md`; model spend $0.70).

- **Issue:** https://github.com/landley/toybox/issues/572 — heap-buffer-overflow in `patch` (`unquote_file`, `toys/posix/patch.c:287`), open since 2025-10-03, no PR.
- **Patch:** `cases/open_bugs/landley_toybox/572/proposed.diff` (worker H2·w1 of `runs/open_bugs_fix2/project_572.json`); applies cleanly to upstream HEAD `6a0c0ef`.
- **My review:** the bug is that an escape sequence can consume the last character, so the loop steps onto the terminator and its `if (!s[1])` check reads past the end and keeps writing. The patch pre-scans to the closing quote with the same escape rules and exits with the existing "bad %s" error on an unterminated name, then allocates exactly what will be written. It is correct but verbose; the one-line equivalent, which you may prefer to send, is to make the loop's check `if (!*s || !s[1]) error_exit("bad %s", filename);`. The gate's evidence is weak here (the reproducer only: toybox's tests are not wired up in our setup), so test it with `make test_patch` before sending.
- **Project AI policy:** none stated in the repository. toybox is maintained by one person by mailing list and GitHub; if you submit, say plainly that the fix was found with an AI tool and reviewed by you.

Options: (a) you submit it (or the one-line version) under your name with that disclosure; (b) leave it — the result stays in the README either way. I will not post, comment, fork or open a PR.

**Update 2026-10-25 (review #7):** the one-line version is now packaged and tested: `cases/open_bugs/landley_toybox/572/SUBMISSION.md` (format-patch file with your git identity as author, commit message, and a two-sentence AI-assistance disclosure). Gate run with no model calls (`runs/open_bugs_572_manual/gate.json`): the one-liner and H2·w1 both clear the reproducer, both are proven compiled into the binary, and both pass all 13 of toybox's own `patch` tests (13/13 on the unpatched build too, with an ASan-only test build; with UBSan, 12 tests fail at HEAD from an unrelated report in `lib/xwrap.c:428`). Recommendation: send the one-liner. Still your decision; I post nothing.

**Update 2026-10-25 (review #8, before the repo goes public):** the committed `.patch` now says `From: <your git identity>` and `SUBMISSION.md` no longer names your email; the copy with your real identity is `0001-patch.private.patch` in the same directory (gitignored, `*.private.*`). If you send the patch, use that copy or set the author with `git commit --amend --reset-author`. Note: your email is still the author email of all existing commits, and in one earlier version of the patch file in history; removing it would need the history rewrite in QUESTION 0012 (default: no rewrite).

## QUESTION 0018 — Leakproof in GitHub Actions: please add the secret and press Run (about 3 minutes)
2026-10-25, per strategist review #9 order 3. Two workflows are in the repo: `demo-fuzz` (builds the csvsplit fuzzer, fuzzes it for at most 120 s, uploads the crash inputs, fails when it finds one) and `leakproof-fix` (runs after a failed `demo-fuzz`: builds the gate's toolchain image, runs `leakproof fix` on the first crash input, publishes the evidence bundle as the job summary). Only this repository can run it, no pull-request trigger exists, the key is never printed, and model spend is capped at $0.10 per run (the local demo costs $0.01).

Your clicks on github.com/samsundar989/nebius-hackathon:
1. **Settings → Secrets and variables → Actions → New repository secret.** Name `NEBIUS_API_KEY`, value: your Token Factory key (the same one as in `.env`). Add secret.
2. Same page, **Variables** tab → **New repository variable.** Name `NEBIUS_PROJECT_ID`, value: the `aiproject-…` id from `.env`. Add variable.
3. **Actions → demo-fuzz → Run workflow** (branch `main`) → Run workflow. When it finishes red ("found a crash"), `leakproof-fix` starts by itself; it takes about 10 minutes.

Then tell me (`## ANSWER 0018`), or I will see the run when the repo is public. Default if not done: the README keeps saying the template has not run on GitHub.

## QUESTION 0019 — Live runs on the dashboard during judging (Dec 1–15)? (money; default: off)
2026-10-26, per strategist review #11 order 5. The demo service can run one real Juliet fix per click (about $0.01–0.02 each: Ultra plan, two Lightning workers, the gate). It is now safe to leave on: `DEMO_TOTAL_USD` (default $2.00) and `DEMO_DAILY_USD` (default $0.50) stop live runs before any model call, plus 25 runs a day, 3 per visitor per 10 minutes, one at a time, and only the Juliet ids in `service/juliet/cases.txt`. When live runs are off, asleep or out of budget, the dashboard's button shows a real earlier run, labelled "recorded run" with the reason.

One honest limit: the caps are kept in memory, and Render's free instance restarts after it sleeps, which resets them. The real bound over the judging window is the daily cap × the days live runs are on (with the defaults, at most $0.50 a day; $7.50 over 15 days if someone woke it every day). Set `DEMO_DAILY_USD=0.15` for a ~$2 worst case.

Options: (a) turn live runs on (`DEMO_ENABLED=true` in Render's environment) with `DEMO_DAILY_USD=0.15`; (b) leave them off and keep the labelled recorded runs. **Default if no answer: (b), off.**

## QUESTION 0020 — Two partial fixes for still-open bugs are packaged (your decision; nothing has been posted)
2026-10-26, per strategist review #13 order 3 (open bugs round 3, full product path). Two verified fixes are correct for the sanitizer finding but cover only part of their issue, so their commit messages say `Part of #N`, not `Fixes`:

- **cesanta/elk #82** — https://github.com/cesanta/elk/issues/82. One line in `next()`: stop reading after an unclosed string at the end of a bounded slice (the issue's own suggestion for strings). The issue's second defect (numbers parsed past `len`) is not fixed. elk's unit test already fails at upstream HEAD, so only the reproducer verified it. Package: `cases/open_bugs/round3/cesanta_elk/generated/` (patch applies to upstream `71a86fa`).
- **me7alix/utf8.h #1** — https://github.com/me7alix/utf8.h/issues/1. `utf8_decode` stops at the terminator before reading each continuation byte and returns U+FFFD. The issue's other requests (reject overlong, surrogate and non-continuation sequences) are not done. Package: `cases/open_bugs/round3/me7alix_utf8.h/generated/` (applies to upstream `c08d482`).

Neither repository states an AI-contribution policy. Options: (a) send one or both under your name with the disclosure in each SUBMISSION.md, saying plainly what is and isn't fixed; (b) leave them. **Default if no answer: (b), nothing is sent.**
