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
