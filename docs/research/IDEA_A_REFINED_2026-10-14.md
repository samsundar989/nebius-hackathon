# Idea A, refined — "Evidence-gated memory engineer for C++/CUDA"

Date: 2026-10-14 (Day 1 of 17). Builds on `research/HACKATHON_RESEARCH_BRIEF_2026-10-13.md`. Three research passes today: (1) prior art in AI perf/kernel agents, (2) memory-safety repair prior art + profiler feasibility in cloud containers, (3) Nebius Sandboxes/Serverless documentation-level deep dive.

---

## 1. Decision summary

**Pivot the primary focus from "make C++/CUDA faster" to "fix memory defects in C++/CUDA with machine-verified evidence" — and keep performance as a deterministic, secondary mode.**

The product: an autonomous agent that takes a real repository plus a sanitizer/profiler finding (ASan/LSan/UBSan crash, LeakSanitizer report, Valgrind/heaptrack report, or `compute-sanitizer` memcheck/leak-check/racecheck report for CUDA), reproduces it, has Nemotron 3 Ultra root-cause and rank repair hypotheses, fans out parallel Nemotron 3.5 Lightning workers that implement each hypothesis in branched Nebius Sandboxes from one checkpoint, and then runs every candidate through an evidence gate it cannot see or modify: sanitizer-clean on the reproducer, project tests pass, differential output on benign inputs, a short re-fuzz, and a "safe-fix" check (no new UAF/double-free/leak introduced). Only candidates that survive become a PR carrying before/after sanitizer logs, the rejection funnel, and the cost ledger. A hosted dashboard shows every run's hypothesis tree, gate results, and spend.

One-liner options: "Verified fixes, or nothing." / "Trust the evidence, not the model."

## 2. The three research findings that drove the pivot

1. **Speedup claims are the thing judges have learned to distrust.** KernelBench-Verified (Jul 2026): under a hardened harness *no* frontier model beats 1.0× geomean on CUDA kernels (GPT-5.5 falls from 1.43× to 0.88×). CUDA-L1: 32.8% of its first RL kernels cheated the timer. PERFOPT-Bench: a raw 492.8× collapsed to ~1.1× after verification. Sakana's "AI CUDA Engineer" was publicly walked back. Repo-level perf benchmarks (GSO, SWE-Perf) show <5% success even for frontier agents. A Nemotron-based perf optimizer built in 17 days will produce few verified speedups, and the NVIDIA system-software judges know this literature. (Nemotron 3 has no published KernelBench/ComputeEval score at all.)
2. **Memory defects have a binary, deterministic oracle and real, Docker-reproducible data.** Sanitizer crash → patch → sanitizer clean + tests + differential check needs no clocks, counters, or statistics. ARVO provides 6,138 reproducible OSS-Fuzz C/C++ memory bugs (one `docker run` each); AutoPatchBench-Lite (113), PATCHBENCH (213), Juliet (public domain, thousands of CWE-401/415/416 cases) exist too. Published baselines let us quantify: CodeRover-S 61% plausible / ~45% truly correct; PATCHBENCH best 59%; AIxCC finalists 68% patched; Google's production system 15%. Memory **leaks** are the easiest class for LLMs (NIST study: ~half of all correct LLM patches were CWE-401), so a leak-led agent can credibly show >80% verified on leaks, with UAF/double-free as the harder tail.
3. **Every tool the memory track needs runs unprivileged in exactly the environments we have.** ASan/LSan/UBSan/TSan, Valgrind, heaptrack, cachegrind run in Nebius Sandboxes (microVM, full root, no GPU); `compute-sanitizer` runs on Nebius Serverless L40S jobs with no special permissions. The CUDA-perf flagship tool `ncu` is confirmed blocked on RunPod, undocumented/unverified on Serverless Jobs, and only reliable on the local 5090 — a demo only reproducible on one desk is a weak hackathon story.

The verification-inflation finding is the pitch: PATCHBENCH shows 83% of LLM patches silence the reproducer but only 45% are actually correct; AutoPatchBench shows ~60% "generated" vs 5–11% verified. An agent whose core loop *is* the evidence gate is what the literature says is missing — and that is literally Samuel's day-job harness, productized.

## 3. Prior art and where we differ

| Existing | What it is | What it lacks / how we differ |
|---|---|---|
| Google "AI-powered patching" (15% of sanitizer bugs fixed), Google ECO | Internal production systems | Closed; ours is open, reproducible, on Nebius Sandboxes with a published gate |
| CodeRover-S, AutoCodeRover, AIxCC CRSs (Atlantis, Buttercup) | Research/competition systems for OSS-Fuzz memory bugs; 55–75% plausible, 40–60% correct | Not products; no PR-ready evidence bundle; frontier/closed models; none use Nemotron or branched sandboxes; AIxCC cost ~$152/task |
| AutoPatchBench, PATCHBENCH, ARVO, Juliet | Benchmarks/datasets | We adopt them as our eval set and verifier design, we don't compete with them |
| Codeflash | Only shipped "verified PR" product (Python/JS/Java perf) | No C/C++, no memory safety, closed verifier |
| GitHub Copilot Autofix | CodeQL alert → suggested fix | Static alerts, no runtime reproduction/verification loop |
| KernelFalcon (Meta), STARK, GEAK, Stanford test-time search | Parallel-worker kernel agents | Perf-only, op-level, no anti-cheat; we borrow the branching skeleton |
| Hackathon field (~20 Python repair agents; `breakwater` adversarial perf red-team) | Sandboxed test-verified Python fixes | Nobody does C/C++/CUDA, sanitizers, or memory; we absorb breakwater's idea as a built-in adversarial stage |

Novel claims we can honestly make: first open, Nemotron-powered, sanitizer-driven repair agent for C++ **and** CUDA (via compute-sanitizer) whose verifier is independent of the worker; first raw-vs-verified funnel published for Nemotron on ARVO; first use of Nebius Sandboxes' checkpoint-and-branch for parallel hypothesis repair with the gate run offline (`networking.enabled=false`).

## 4. Focus areas, ranked (what's in, what's stretch, what's cut)

**Core (must ship):**
1. **C/C++ memory leaks (CWE-401) and memory-safety crashes (CWE-416 UAF, CWE-415 double free, CWE-121/122 overflows, CWE-476 NPD) from sanitizer reports.** Eval on an ARVO sample (40–60 cases weighted to 401/415/416/122) + Juliet as harness unit tests. This is the headline number.
2. **The evidence gate** (section 6) — the product's identity. Workers never see it.
3. **CUDA memory defects via `compute-sanitizer`** (memcheck OOB, leak-check `cudaMalloc` without free, racecheck, initcheck) on Nebius Serverless L40S jobs — 10–15 cases (hand-built from CUDA samples with injected bugs + any real GitHub issues). This is the NVIDIA-native extension and the reason to use AI Cloud, not just Token Factory.
4. **Hosted dashboard + PR output** (Design criterion).
5. **Nemotron tiering + cost-per-verified-fix leaderboard** (Nano triage / Lightning workers / Super planner alt / Ultra root-cause) — new numbers for NVIDIA judges.

**Stretch (only after core is green, ~Day 12+):**
6. **Memory footprint mode** — heaptrack/massif peak-RSS and allocation-count reduction with deterministic acceptance (same theme: memory). Deterministic metric, no clocks needed.
7. **CPU hot-loop mode** with cachegrind instruction counts (SQLite/rustc-perf style) — deterministic proxy for speed, no privileges needed. Only if time remains.
8. Tavily bonus: ground the planner with upstream API docs / similar fixed issues (map→extract, citations in PR). Decide Day 10.

**Cut (do not attempt in this hackathon):**
- Wall-clock CUDA kernel speedups as a headline (needs ncu/clock locking/L2 flush/hidden-input suites; literature says the numbers collapse). Mention as future work; optionally one 5090-only appendix experiment if everything else is done.
- GPU-side real-time profiling UI, multi-GPU, non-Linux targets.

## 5. The loop (what the agent actually does)

```
intake:   repo URL + reproducer (crash input / failing test / sanitizer log)  [or: scan mode — build with ASan+LSan, run tests/fuzz seeds, harvest findings]
repro:    Sandbox from baseline image UUID: build with sanitizer flags, run reproducer, capture report → canonical "finding" (CWE guess, stack, alloc site, free site)
plan:     Nemotron 3 Ultra (thinking on, 1M ctx: finding + relevant files + call graph slice + ownership notes) → ranked hypotheses as JSON (validated, retried)
branch:   for each hypothesis (N≈4–6, semaphore ≤ whoami.instance_max_concurrency): Lightning worker edits in a disposable run from the SAME baseline UUID; on green build → saved checkpoint (tag perfagent/<run>/<hyp>)
gate:     separate process, read-only harness, networking off:
          (1) build clean under ASan+UBSan(+LSan) ; (2) reproducer no longer trips sanitizer ; (3) project tests pass ;
          (4) differential: benign inputs produce byte-identical outputs vs original ; (5) short re-fuzz (libFuzzer/AFL++ 1–3 min) on the harness finds no new report ;
          (6) safe-fix check: no new UAF/double-free/leak under sanitizer on the full test run ; (7) diff-scope check: no edits to tests/harness/build flags that weaken checks ; (8) LLM trajectory audit → FLAG only (never gates)
rank:     survivors ranked by gate score, diff size, and model cost; losers kept with named rejection reason
deliver:  PR with patch, before/after sanitizer logs, funnel (N tried → k built → j silenced → i verified), cost ledger, model used; dashboard run page
```

CUDA path: same loop, but the gate step runs inside one batched Serverless Job (`nvidia/cuda:*-devel`, `gpu-l40s-a 1gpu-8vcpu-32gb`, preemptible) with `compute-sanitizer --tool memcheck|racecheck|initcheck|synccheck --leak-check full`; compile/static checks still happen in the CPU sandbox (nvcc needs no GPU).

## 6. Evidence gate — techniques borrowed (with their source)

- Run candidate in a fresh process before any reference; cloned inputs; poisoned output buffers (Kevin-32B, SOL-ExecBench).
- Hidden benign-input corpus never shown to workers; differential output equality (ACCLAIM, GSO, PATCHBENCH semantic check).
- Re-fuzz with the original harness after the patch (AutoPatchBench, PATCHBENCH directed+undirected fuzzers).
- "Safe repair" criterion: a leak fix must not introduce UAF/double-free (SAVER/MemFix line of work) — enforced by running the full suite under ASan after the patch.
- Lock tests/harness read-only; grader owned by the orchestrator, never the worker (CUDA Agent, AgentKernelArena, Nemotron 3.5 Lightning guide).
- Six-check trajectory audit prompt: test tampering, hard-coding, API interception, reduced workloads, public-test-only, hidden-state dependence (PERFOPT-Bench) — flags, does not gate (EquiBench: LLM judges are 64–76% reliable; CodeRover-S: LLM-as-judge F1 0.52–0.73).
- Report raw vs verified side by side and the rejection funnel (KernelQuest rejected 565/1200; Codeflash discards ~15:1).
- For the stretch perf modes: cachegrind instruction counts (SQLite), `perf stat instructions:u` where a PMU exists (rustc-perf), bootstrap CI of the ratio (Kalibera & Jones), SWE-Perf's Mann-Whitney + 5% minimum effect.

## 7. Nebius / NVIDIA usage map (the "Technological Implementation" story)

| Primitive | Where we use it | Why it matters to judges |
|---|---|---|
| Token Factory — Nemotron 3 Ultra | root-cause + hypothesis planning over 1M-token context (repo slice + logs) | NVIDIA's flagship; long-context use nobody else shows |
| Token Factory — Nemotron 3.5 Lightning | parallel patch workers ($0.06/$0.24) | NVIDIA's "execution layer" narrative; cost story |
| Token Factory — Nano | finding triage / CWE classification / dedup | cheap tier routing done for a reason, with numbers |
| Token Factory — Batch API (50% off) | offline eval re-runs and leaderboard | non-obvious use; Nebius judges like published spend |
| Sandboxes (Contree) | baseline image per repo (`contree build`), branch N hypotheses from one UUID, gate run with `networking.enabled=false`, artifacts downloaded from saved checkpoints | the most Nebius-native agentic feature; almost no cookbook uses branching |
| AI Cloud Serverless Jobs | batched `compute-sanitizer` runs for CUDA cases on preemptible L40S; results to an Object Storage bucket | AI Cloud usage (few entrants have any); Serverless TPM is a judge |
| NVIDIA compute-sanitizer | the CUDA oracle | NVIDIA tool, deterministic, unprivileged |
| Local RTX 5090 (workerq) | fast inner-loop CUDA runs during development; optional ncu appendix | honesty: cloud numbers are the ones in the PR |
| (optional) Tavily | upstream API docs / prior fixes as cited grounding | bonus only if meaningful |

## 8. Eval plan and target numbers

- **Juliet 1.3 (public domain):** 100–200 CWE-401/415/416 cases → harness unit tests; expect ~100% (say so; it's a smoke set, not the headline).
- **ARVO sample:** 40–60 cases, weighted to CWE-401, 415, 416, 122; one `docker run arvo/<proj>:<id>-vul` each → convert to a Sandbox image via `contree images import`. Report: built / silenced / verified rates per CWE, per model (Lightning-only vs Ultra+Lightning vs Super+Lightning), $ per verified fix, wall time. Compare against CodeRover-S (61%/45%), PATCHBENCH (59%), Google (15%).
- **CUDA set:** 10–15 cases (injected bugs into CUDA samples: OOB global access, missing cudaFree, race on shared memory, uninitialized device memory) + any real issues found; report verified rate.
- **Live PRs:** pick 2–3 still-open OSS-Fuzz/ARVO bugs in small, active C libraries and open real PRs before the deadline (CodeRover-S's "5 merged PRs" move). Even one merge is a headline.
- Surprising findings to look for and publish: silencing-vs-verified gap for Nemotron; which CWE Nemotron fixes "safely"; Ultra-vs-Lightning cost/verified-fix; how often workers try to edit tests (the diff-scope check will catch it).

## 9. Honing per judging criterion

- **Technological Implementation (25%)** — the usage map above; README architecture diagram; "why each model where" table with measured cost; Sandboxes branching shown in the video with the lineage view; Serverless job IDs and bucket outputs linked. Record the mandatory feedback as we go (Sandboxes SDK quirks: `disposable` defaults differ across SDK/REST/CLI/MCP; `ENTRYPOINT` dropped on import; mini-swe-agent example broken; TF `json_schema` support untagged for Nemotron; thinking toggle undocumented; no spend cap/402; jobs bill during STARTING).
- **Design (25%)** — complete product: CLI (`<name> fix <repo> --repro …`), GitHub-App-style PR with evidence bundle, hosted dashboard (run list → run page: finding, hypothesis tree, gate matrix per candidate, funnel, cost; read-only + a rate-limited "run on sample bug" button with a daily budget guard). Static SPA on Cloudflare Pages/Fly (~$0–6 for the window) reading run JSON from a bucket; optionally spin up a Nebius Endpoint during the recording.
- **Potential Impact (25%)** — audience: every C/C++ team drowning in sanitizer/fuzzer findings (OSS-Fuzz has thousands open), security teams, HPC/CUDA teams; ~70% of serious CVEs are memory-safety bugs (Microsoft/Chromium statistics); AIxCC patches cost ~$152 each — ours should be well under $1. Demo supports the claim: real ARVO bugs, real PRs.
- **Quality of Idea (25%)** — frame as "the gate is the product": every fix ships with its evidence; raw-vs-verified funnel chart; cross-domain (CPU sanitizers + CUDA compute-sanitizer) under one verifier; Nemotron leaderboard nobody has published. Cite KernelBench-Verified, PATCHBENCH, AutoPatchBench, CodeRover-S in the README as design inputs. Avoid "AI engineer" naming.
- **Video (3 min)** — 0:00 problem (one real ASan trace; "83% of AI patches silence the crash, 45% are right"); 0:30 run it live on a real bug: hypotheses branch in Sandboxes (lineage view), gate rejects two for named reasons, one survives; 1:45 CUDA case on a Nebius Serverless job with compute-sanitizer; 2:15 dashboard + PR + numbers table; 2:45 say aloud "Nemotron 3 Ultra and 3.5 Lightning on Nebius Token Factory, Sandboxes, Serverless Jobs".

## 10. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| Sandboxes beta access delayed | Request today; Discord + contree@nebius.com; build a local Docker runner with identical interface (`Runner` abstraction) so the loop works Day 2 regardless; swap in Contree when approved |
| ARVO images large / slow to import into Contree | Start with 10 small-project cases; run the rest in local Docker; import only the baseline image once per repo |
| Nemotron weak on hard UAF cases | Lead with leaks (easy class); report honest per-CWE rates; this is still a result |
| `json_schema`/thinking toggle quirks on Token Factory | Schema-in-prompt + validator + retry; smoke-test Day 0 |
| Serverless job startup "several minutes"; bills during STARTING | Batch all CUDA cases of a round into one job; cap `--timeout 1h`; cancel if STARTING > 10 min |
| Cost | Sandboxes free in beta; TF ~$0.20–0.30 per run; one L40S preemptible job ≈ $0.15–0.25; full eval ≈ $10–20 total; dashboard ≈ $0–6 |
| Day-job IP | Clean-room build; no code or configs from the employer harness; note "inspired by common practice" only |
| Scope creep | Core = sections 4.1–4.5; stretch modes only after the ARVO eval runs end-to-end |

## 11. Day-0 / Day-1 setup (Samuel, in order)

1. Token Factory: sign in at https://tokenfactory.nebius.com → add billing/card → redeem `NEBIUS-DEVPOST-GLOBAL26` via https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 → check Transactions.
2. Builders Program: https://dev.nebius.com/builders → verify email → redeem the +$25 TF and +$25 Tavily codes now (90-day expiry).
3. **Request Sandboxes beta**: https://tokenfactory.nebius.com/sandboxes/about → "Join Beta" (mention the hackathon). Join Discord https://discord.gg/eXYTGhgnhK; if no answer in 24 h, post there and email contree@nebius.com. Access is per project — request it for the project whose API key you'll use.
4. API key: https://tokenfactory.nebius.com/project/api-keys; project ID from Project settings. `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=… NEBIUS_AI_PROJECT=$NEBIUS_PROJECT_ID`. Never commit; `.env` + `.gitignore`.
5. Nebius AI Cloud: https://console.nebius.com → add card ($25 charged, becomes balance) → Administration → Limits → Quotas: confirm eu-north1 L40S + preemptible VM quota → create an Object Storage bucket + access key.
6. Local: confirm Docker (Desktop/WSL2) on the 5090 box; that is the fallback runner and the CUDA dev loop.
7. Then Claude Code takes over from the kickoff prompt: smoke tests (TF chat/thinking toggle/json_schema/tool calls/batch; Contree whoami/import/branch; one Serverless `nvidia-smi` job with timing), repo skeleton (MIT, README with mandatory sections, cost ledger), Runner abstraction (local Docker ↔ Contree), Juliet smoke set.

## 12. 17-day skeleton

- Days 1–2: accounts, smoke tests, repo skeleton, Runner abstraction, Juliet smoke set (harness unit tests).
- Days 3–5: intake/repro + planner (Ultra) + workers (Lightning) + branching; first end-to-end fix on Juliet, then on 5 ARVO cases.
- Days 6–8: the evidence gate (all 8 checks), rejection reasons, funnel; ARVO sample to 20–30 cases; PR generator.
- Days 9–10: CUDA path (compute-sanitizer) on Serverless Jobs, batched; 10 CUDA cases.
- Days 11–12: dashboard (static SPA + run JSON), budget guard, demo button; model leaderboard via Batch API.
- Days 13–14: full ARVO eval (40–60), live PRs on 2–3 open bugs, stretch modes only if green.
- Days 15–16: README numbers tables, architecture diagram, feedback write-up, video script + recording, Devpost form draft.
- Day 17 (Oct 30 morning): submit by 12:00 PM CDT — aim to submit Oct 29.

## 13. Open questions for Samuel

1. Confirm the pivot: memory-first (sanitizer-driven C/C++ + CUDA compute-sanitizer), perf only as a deterministic stretch mode?
2. Local box: Windows with WSL2 + Docker Desktop available? (needed for the fallback runner and 5090 CUDA dev loop)
3. Name — pick or veto: "Leakproof", "Tourniquet", "Hardline", "Clearcut".
4. OK to top up Nebius AI Cloud by $25 (it becomes balance; the CUDA path needs it; otherwise the CUDA gate runs only on the local 5090 and the AI Cloud story disappears)?
