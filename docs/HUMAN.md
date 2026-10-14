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
