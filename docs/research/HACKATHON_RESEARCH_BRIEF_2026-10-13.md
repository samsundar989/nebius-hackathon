# Nebius x NVIDIA Global AI Hackathon — Research Brief

Researched 2026-10-13 (Day 0 for us). Sources: all Devpost pages (overview, rules, resources, updates, 47 forum threads, FAQ, gallery, participants), Token Factory console verified live in Chrome, Nebius/NVIDIA docs and blogs, ~150 public participant repos on GitHub, Devpost project pages, past Nebius/NVIDIA hackathon winner write-ups, judge bios.

---

## 1. The competition in one paragraph

Online Devpost hackathon sponsored by Nebius (GPU cloud + "Token Factory" model API) with NVIDIA. You build any AI project that (a) makes a runtime call to an NVIDIA open model through Nebius Token Factory *or* runs on Nebius AI Cloud, and (b) fits one of four tracks. You submit a public repo (OSI license), a <3-min YouTube video, a hosted demo URL, a text description, and mandatory written feedback on the Nebius/NVIDIA tools. Human judges (23 NVIDIA/Nebius/Tavily staff) score four equally weighted criteria 1–5. There is no leaderboard, no automated scoring, no public vote.

## 2. Dates (Samuel's time zone, CDT)

| Milestone | Date |
|---|---|
| Submission window opened | Aug 26, 2026 |
| **Submission deadline** | **Fri Oct 30, 2026, 12:00 PM CDT** (10:00 AM PDT) — 17 days from Oct 13 |
| Judging | Dec 1 – Dec 15, 2026 (demo URL must stay working through Dec 15) |
| Winners announced | ~Jan 11, 2027 |

Samuel is already registered (confirmed in Chrome: "You're registered for this hackathon"). 22,828 registrants on Oct 13.

## 3. Prizes ($50,000 cash + hardware)

| Prize | Amount | Count |
|---|---|---|
| Grand Prize (across all tracks) | $20,000 | 1 |
| 2nd Place | $10,000 | 1 |
| 3rd Place | $6,000 | 1 |
| Track Winner (one per track) | NVIDIA Jetson Orin Nano (hardware, no cash) | 4 |
| Best Use of Tavily (bonus) | $3,000 | 1 — needs a functional runtime Tavily API call |
| City Winner (bonus) | $500 | 20 — requires in-person attendance at a Builders & Brews event (none in Austin; last one was LA Oct 13) → **not available to us** |
| Most Valuable Feedback (bonus) | $100 + NVIDIA swag | 10 |

**Stacking rule (organizer-confirmed):** a project wins EITHER one overall award (1st/2nd/3rd) OR one track award + one bonus award. Never overall + bonus.

Payment: W-9 + affidavit within 10 business days of notification; paid within ~60 days.

## 4. How we are scored (this is the whole game)

**Stage 1 — pass/fail.** Genuine attempt at the chosen track (not a relabeled unrelated project) and genuine use of the required platform (Token Factory or AI Cloud + an NVIDIA open model).

**Stage 2 — four criteria, 25% each, scored 1–5:**
1. **Technological Implementation** — quality of the build AND how effectively it uses Nebius Token Factory / AI Cloud and NVIDIA Nemotron (or other NVIDIA open models).
2. **Design** — a complete, coherent product experience, not a technical proof of concept.
3. **Potential Impact** — a credible, specific case that it solves a real problem for a real audience; the demo supports the claim.
4. **Quality of the Idea** — creative, non-obvious use of the models; team understands the problem space.

Tie-break: compare criteria in the order above, then judges vote.

**Per-track "beyond the basics" (from the official "Here's how judging works" update):**
- Coding & Agentic Engineering: a code-completion wrapper is the baseline; they want an agent that *plans, writes, tests and iterates on a real repo with minimal human input*.
- Best Apps & Agents: a single API call is the baseline; they want multi-step autonomous workflows chaining tools end-to-end.
- Personal AI: a chatbot with a system prompt is the baseline; they want context that persists across sessions and real actions taken.
- Physical AI: scripted demos are the baseline; they want hardware reacting live to real-world input (simulation-only is allowed).

**Critical practical facts about judging:**
- Rules say judges *may* evaluate solely from the description, images and video, and will not watch more than 3 minutes of video. Assume they will NOT run the code. The video + README + Devpost text ARE the submission.
- Organizer tips: name "Nebius Token Factory" and the exact NVIDIA model in the description, in the Built-With tags, AND spoken aloud in the video; the video is a pitch (problem → working solution → who it's for → how Nebius/NVIDIA are used), not a tutorial; no hard-coded keys; human-sounding project name; submit early.
- Feedback on the tools is a mandatory submission field: what you used each tool for, what worked, what needs work, the zero-to-hello-world onboarding experience, whether you'd build with it again. Several judges own onboarding (PMM/DevRel), so specific, measured feedback is a scoring lever.

## 5. Submission checklist (every item required)

1. Working project that calls an NVIDIA open model via Token Factory (`https://api.tokenfactory.nebius.com/v1/`, OpenAI-compatible) **or** is deployed on Nebius AI Cloud (Serverless Jobs / Endpoints / DevPods). Calling Nemotron through OpenRouter/HuggingFace/NVIDIA's own API does NOT count. Everything else (frontend, other backends) may live anywhere.
2. Track selection (one track per submission; multiple substantially different submissions allowed).
3. Text description.
4. Demo URL (hosted app / test build), accessible through Dec 15; credentials provided if private. Not required for Physical AI.
5. Public repo (GitHub/GitLab/Bitbucket) with OSI license visible at top (MIT/Apache-2.0/MPL), README with setup/run instructions, and an explicit section on how NVIDIA models + Token Factory + other Nebius services were used.
6. Demo video ≤ 3 min, public on YouTube, shows project running; no unlicensed music/trademarks.
7. Written feedback on Token Factory / AI Cloud / each NVIDIA tool used.
8. If pre-existing project: written explanation of what was significantly updated during Aug 26–Oct 30.
9. Team: solo allowed; no max team size; one Representative submits and receives prize. Entrant keeps IP. Pre-existing code allowed only with significant in-window updates + changelog.

## 6. The tech stack (verified Oct 13, 2026)

### Token Factory — NVIDIA models actually in the public catalog (checked in Chrome; 25 public endpoints total)

| Model ID (exact) | Context | $/M in / out | Speed | Notes |
|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262K | 0.06 / 0.24 | 60 tok/s | fp8; good cheap tool-caller; weak multilingual |
| `nvidia/Nemotron-3_5-Lightning` | 1M | 0.06 / 0.24 | ~314 tok/s | 30B-A3B; SWE-bench Verified 51.6 (vs Nano 38.8); trained with OpenClaw/Hermes harnesses; **best cheap worker** |
| `nvidia/nemotron-3-super-120b-a12b` | 256K | 0.30 / 0.90 | 127 tok/s | fp4; NVIDIA's recommended planner/orchestrator; SWE-bench ~60.5 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 1M | 1.00 / 3.00 | ~523 tok/s | fp4; SWE-bench Verified ~70–72, Terminal-Bench 2.1 ~56; best for planning/reasoning; strong long-context |

Not on Token Factory: Nemotron 3 Nano Omni (several competitor READMEs claim it — likely via another provider, which would not qualify), Nemotron Speech/Retriever/Safety, GR00T/Cosmos (those run as GPU jobs on AI Cloud, not as TF endpoints).

Known Nemotron quirks to design around (and to put in the feedback section):
- Reasoning/thinking is ON by default → latency/cost. Toggle via `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` (Super: `low_effort`, Ultra: `medium_effort`). Test that Token Factory passes this through — undocumented on Nebius side.
- Ultra sometimes stops before emitting required structured output (CodeRabbit measured very high retry rate) → always validate + retry.
- `response_format: json_schema` is not tagged as supported on the Nemotron cards → test early; put the schema in the prompt too.
- Rate limits are dynamic (baseline ~60 RPM / 400K TPM, auto-raise with utilization). Participants report 4xx under concurrency and no spend cap (402 errors when balance hits zero). Build backoff + budget guard.
- No Nemotron fine-tuning on Token Factory (LoRA/full FT only for Qwen/Llama/gpt-oss/DeepSeek/Gemma).

Other Token Factory primitives (distinctive, under-used by competitors):
- **Sandboxes ("Contree", beta, free during beta, request access at tokenfactory.nebius.com/sandboxes):** isolated microVMs for agent code execution; Python SDK `contree-sdk`, CLI, REST, and an MCP server; images → run → optionally snapshot as new image; **checkpoint & branch** (try N attempts in parallel from one state, roll back); 7,000+ preloaded SWE-bench environments. Some participants report 403/access delays → request on Day 0 and have a fallback.
- **Batch API** (`/v1/batches`, JSONL, 50% discount, 24h window) — ideal for offline evals.
- Embeddings (`Qwen3-Embedding-8B`), rerank, Responses API, dedicated endpoints, observability.
- Other catalog models usable alongside Nemotron: DeepSeek-V4-Flash ($0.14/$0.28), GLM-5.3-Flash (vision, $0.15/$0.50), Kimi-K2.7-Code, Qwen3.8-27B (vision), MiniCPM-V-4.5 (vision/OCR), gpt-oss-120b, Hermes-4-405B.

### Nebius AI Cloud Serverless
- **Jobs:** container runs on a GPU/CPU preset with timeout 1h–168h; billed only while running; preemptible GPUs from ~$0.65–0.79/hr (L40S / RTX PRO 6000 / H100), on-demand H100 $4.50/hr, L40S ~$1.35–1.55/hr, CPU ~$0.012–0.015/vCPU-hr. Single node. Mount buckets/shared FS.
- **Endpoints:** managed HTTPS URL per container port; **no autoscaling / scale-to-zero yet**; billed from create to delete (stop pauses GPU billing). Use `--auth token` (default is none).
- DevPods/"Devlabs" = dev VMs.
- Credits: none granted for AI Cloud; requires a $25 top-up before requesting cloud credits. Budget our own money and report spend.

### NVIDIA tools named in the tracks
- **Hermes Agent** (NousResearch, ~253K stars, MIT): CLI/TUI + messaging gateways (Telegram/Discord/Slack/WhatsApp…), self-created skills, agent-curated memory, cron, subagents, any OpenAI-compatible endpoint → works with Token Factory.
- **NVIDIA NemoClaw** (~22K stars, Apache-2.0, "alpha"): one-line installer that runs an agent (OpenClaw default, Hermes, LangChain Deep Agents) inside an OpenShell sandbox with managed inference + network policy + snapshots; supports "other OpenAI-compatible endpoint" → Token Factory. Nebius ran a webinar (Jun 10) doing exactly NemoClaw on AI Cloud VM + Token Factory + Tavily + Slack.
- **NVIDIA OpenShell** (~10K stars, v0.1.x): sandbox runtime with syscall/FS controls and network allowlists; SDKs Py/TS/Go/Rust.
- **Physical AI:** GR00T N1.7 (3B VLA, commercial license), Cosmos 3 (Nebius is a named inference partner), Cosmos Reason 2, SONIC (humanoid motion), Alpamayo 1 / 2 Super (driving VLA). Nebius "Physical AI Workbench" + `npa` CLI exist. Simulation-only entries allowed.

### Tavily (now a Nebius company)
- Endpoints: `/search` (depth, `topic=news`, `time_range`, `include_raw_content`), `/extract`, `/crawl`, `/map`, `/research` (returns `output_schema` JSON, streaming, citations). Headers `X-Project-ID`, `X-Session-Id`, `X-Human-Id` for audit. Official MCP server, agent skills.
- Free tier 1,000 credits/month without card; PAYG $0.008/credit; +$25 credit via Nebius Builders Program.
- Tavily judges are FDEs; almost every competitor uses `/search` once decoratively. Depth = map→extract with provenance, `/research` with `output_schema`, domain filters, session IDs shown in UI.

### Credits & accounts to set up on Day 0
- $25 Token Factory promo: code `NEBIUS-DEVPOST-GLOBAL26` at https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 (billing/card must be completed first; US is supported).
- +$25 Token Factory, +$25 Tavily, $100 LangSmith via Nebius Builders Program: https://dev.nebius.com/builders (credits reportedly expire ~90 days).
- Request Sandboxes beta access: https://tokenfactory.nebius.com/sandboxes
- Nebius Discord (support): https://discord.gg/eXYTGhgnhK · Devpost Discord: https://discord.com/invite/HP4BhW3hnp
- Docs: https://docs.tokenfactory.nebius.com/quickstart · https://docs.tokenfactory.nebius.com/sandboxes/overview · https://docs.nebius.com/serverless · cookbook https://github.com/nebius/token-factory-cookbook · https://dev.nebius.com/cookbook
- Build-session recording (Sep 8, Jacquie Capur): https://youtu.be/j_jEXP2ix2E

## 7. What other teams are building (public evidence, ~150 repos + ~40 Devpost pages)

Scale: 22.8K registrants, heavy student promotion → long tail of low-polish entries; maybe 20–40 serious (hosted demo + video + tests) entries visible so far. Almost all solo.

**Crowded lanes (avoid or out-execute):**
1. Coding track = sandboxed, test-verified Python repair agents on Token Factory Sandboxes (20+ entries: FixFork, PortVerdict, SandForge, branchforge, RepoMedic, Nemesis-CI, CodeGuard, HarnessLab, nemocascade…). Sub-variants already taken: fork-N-candidates-and-race, adversarial/red-team diffs, harness/eval labs, agent safety firewalls, issue→PR bots.
2. "Model proposes, deterministic code decides" + receipts / hash-chained audit logs / JUDGE_REPRO.md — this is now the default house style (clearly AI-coding-agent-generated READMEs). Table stakes, not a differentiator.
3. Tavily + Nemotron cited research agents (the cookbook "deep research" shape) — the obvious project.
4. Personal AI = generic memory + skills + approval gates; most unfinished. Standouts picked sharp niches (Site Memory for installers, Hardware Design Copilot for Verilog, Paperwise for scary mail).
5. Vertical "desk" apps with human sign-off (logistics fraud, cancer navigation, cargo, invoicing, healthcare most common).
6. Nano→Super→Ultra tier routing with cost logging — in nearly every README.

**The polish bar (entries that will likely score 4–5 across the board):** Podrá Navega (cancer navigation, 96% vs 76% eval), Proofline (verified business profiles, 199 tests), Said Who? (quote provenance), VF Logistics (717 tests), FixFork (303 tests, CI, hosted), PortVerdict, NemoFold (1,189 tests), Indie App Ops Agent, OurSpaces.

**Gaps nobody is filling:**
- Physical AI with real hardware responding live (only ~7 entries, nearly all sim/mock; judges have 4 Physical-AI people and the track prize is a Jetson).
- Nebius Serverless Jobs / Endpoints used for real (almost nobody); fine-tuning/distillation on Token Factory inside the window (nobody).
- 1M-context use cases (nobody); Ultra as a genuinely long-running autonomous agent (rare — mostly used as a "critic").
- Hermes Agent / NemoClaw / OpenShell-based Personal AI (named in the track text, in the official build session — essentially zero entries).
- **Compiled-language / systems / performance engineering in the Coding track: nothing on C++/CUDA/GPU kernels/low-latency code** (only a perf-PR red-team and a C++ modernization tool). Sandboxes run containers, so compiled flows are feasible.
- "Where agents get better" — RL environments, trajectory datasets, gyms (only diagnostics labs exist).
- Finance/trading: near-empty (one stub, a poker coach, a PayPal reconciliation desk).
- Tavily depth (map/extract/research with provenance) — rare.

## 8. What past Nebius / NVIDIA judges actually rewarded

- Nebius Serverless AI Builders Challenge (Aug 2026): 1st MediSimplifier (solo; LoRA fine-tunes, 7 parallel ablations, published $320 spend incl. failures, reported LLM-judge κ=0.11); 2nd an eval dashboard that found reasoning models score 0% unless `<think>` is stripped; 3rd Balagan chaos-engineering harness (225 trials, $3.64). Nebius's stated patterns: real problem, fit workload to the platform, publish measured spend incl. failures, report surprising findings, reproducible repo + write-up.
- AWS × NVIDIA "Agentic AI Unleashed" (Devpost, identical 4-criteria rubric, Oct–Nov 2025): Grand Prize Nomi — two freshmen, elder-care sensor system: ESP32 sensors → cloud → Nemotron NIM summaries → React dashboard, honest "challenges" section. Won by being a complete end-to-end product with a real audience, not by model novelty.
- NVIDIA Nemotron Hackathon Seoul (Apr 2026): winner Nota AI; their lesson: quantitative delta vs baseline beats a polished concept; put the demo behind a QR code and spend the pitch on the core method.
- GTC 2026 Agents for Impact: solo student (Loomin: physics → 3D sim with Nemotron Ultra, <3 s responses).
- Cross-cutting: complete product + named audience; measured numbers (cost, latency, accuracy deltas, ablations); deep visible use of the sponsor's distinctive primitives; reproducible repo; solo builders win repeatedly; demo videos are plain screen recordings with a problem-first pitch.

Judges to keep in mind: Nebius DevRel/PMM (Dylan Bristot — business outcome first, pick model per sub-task; AbdulMajed Raja — writes the cookbooks, publishes per-task token cost; Jacquie Capur — ran the build session, onboarding-focused; Rob Spectre — ex-Twilio evangelism, "first win" moments; Joe Sarabia — ecosystem/reference architectures; Mikhail Rozhkov — Serverless TPM), Nebius Physical AI (Evan Helda, Dhruv Diddi), NVIDIA (Johnny Núñez robotics DevRel; Nancy Agarwal / Abhinav Balasubramanian — NIM, data flywheels, evals; several system-software engineers; Aditya Sahu — Jetson), Tavily FDEs (Evan Rimer — "optimize for the next decision", context management).

## 9. Candidate ideas for us (ranked)

Samuel's assets: senior C++/Python engineer in trading systems; RTX 5090 + workerq for local heavy jobs; RunPod credits; an existing strategist↔worker autonomous dev loop; Periscope (code comprehension) work; Claude Code for implementation.

### Idea A (recommended) — Autonomous performance-engineering agent for C++/CUDA code · Coding & Agentic Engineering track
An agent that takes a real repo + a benchmark target, profiles it, has Nemotron 3 Ultra (1M context: whole codebase + profiler output + vendor docs) propose ranked optimization hypotheses, has parallel Nemotron 3.5 Lightning workers implement each one from a shared checkpoint (Sandboxes checkpoint-and-branch, or fallback runners), verifies correctness with the repo's tests + differential testing, benchmarks each variant on consistent hardware (Nebius Serverless Jobs on L40S/H100 preemptible for GPU, plus local RTX 5090), applies rigorous statistics (bootstrap CIs, perf counters, noise floors), keeps only variants that are both correct and significantly faster, and opens a PR with a performance report. Includes an eval suite (10–20 real kernels/hot loops) and a Nano/Lightning/Super/Ultra leaderboard with cost-per-accepted-speedup.
- Why it can win: empty lane; NVIDIA judges love CUDA/perf; uses TF (Ultra+Lightning), Sandboxes, Batch API, AND AI Cloud Serverless Jobs — the deepest possible "Technological Implementation"; naturally produces the measured numbers and surprising findings Nebius judges reward; Samuel's domain credibility (low-latency trading); Tavily can be meaningful (map→extract NVIDIA/Intel optimization docs for the target architecture with citations in the PR).
- Real audience / impact: ML-infra and HPC engineers writing custom kernels; quant/trading devs; anyone with a hot loop. On-brand for Nebius (sells GPUs) and NVIDIA.
- Continuation value: directly useful for kalshi-bot/trading infra; credible product direction.
- Risks: Sandboxes beta access delay (fallback: Nebius Serverless Jobs + local Docker runner); scope creep (limit to a fixed target set); Nemotron may struggle on hard CUDA — honest results are still a win if measured well; "Design" needs a real product surface (CLI + hosted dashboard of runs with hypothesis tree, speedup with CI, correctness status, $ cost).

### Idea B — Calibrated forecasting agent for prediction markets · Best Apps & Agents track (+ Tavily bonus)
Nightly Serverless Job pulls open markets (Kalshi/Polymarket), Tavily `/search` (news, time_range) + `/extract` builds an evidence dossier per market, Nemotron Ultra reasons to a probability with explicit base rates and cited evidence, Lightning does cheap triage; the app tracks Brier score / calibration against resolved markets, shows model-vs-market disagreements, and lets a user drill into the evidence. Batch API for re-scoring.
- Pros: Samuel's domain; rigorous quantitative eval (Brier vs market baseline) differentiates it from the crowded research-agent lane; perfect Tavily fit; long-term value for kalshi-bot.
- Cons: judges may read "prediction markets" as gambling-adjacent; the research-agent shape is the most common; impact story needs care ("decision support for analysts/forecasters", not "make money").

### Idea C — Always-on engineering chief-of-staff on Hermes Agent + NemoClaw/OpenShell + Nebius · Personal AI track
Productize Samuel's strategist↔worker loop as an always-on personal agent: persistent memory across all his repos, reusable skills (recon, experiment dispatch to the local 5090 via workerq or to Nebius Serverless Jobs, report writing), Slack/Telegram gateway, scheduled recon, escalation to the human with decision packets. Runs on a cheap Nebius AI Cloud CPU VM with Nemotron Ultra/Lightning via Token Factory, sandboxed by OpenShell/NemoClaw.
- Pros: the track literally names these tools and nobody uses them; Nebius ran this exact webinar; NVIDIA judges would like NemoClaw adoption; it is a real need Samuel has.
- Cons: Personal AI is full of generic "memory + skills" entries; NemoClaw is alpha; "complete product" is harder to demo in 3 minutes; audience ("solo engineers running many AI-coded projects") is real but narrower.

### Idea D — Physical AI simulation (Isaac Lab / GR00T / Cosmos on Serverless Jobs)
Fewest competitors and the judges want it, but Samuel has no robotics background or hardware; 17 days is too short to learn Isaac Lab, run a real sim pipeline and produce ≥1 min of convincing footage. Only if he wants to learn robotics; otherwise skip.

Possible second submission (allowed if substantially different): B or C as a smaller entry after A is locked, only if time remains.

## 10. Day-0 / Day-1 logistics (regardless of idea)
1. Token Factory account: complete billing (card), redeem `NEBIUS-DEVPOST-GLOBAL26`, join Builders Program (+$25 TF, +$25 Tavily), request Sandboxes beta, create API key, verify `GET /v1/models`.
2. Smoke tests: Ultra + Lightning chat completion; tool calling; `json_schema`; `chat_template_kwargs.enable_thinking` passthrough; rate-limit behavior under 10–20 concurrent requests; Batch API.
3. Nebius AI Cloud: top up $25, try one Serverless Job on a preemptible L40S (measure spin-up time and cost).
4. Create the public repo with MIT license on day one; README skeleton with the mandatory "How we use NVIDIA models / Token Factory / Nebius" section; `.env` + `.gitignore`; cost ledger from the first call.
5. Reserve ~3 days at the end for: hosted demo hardening (budget guard, rate limits, recorded fallback), the 3-minute video, README numbers tables, feedback write-up, Devpost form.
