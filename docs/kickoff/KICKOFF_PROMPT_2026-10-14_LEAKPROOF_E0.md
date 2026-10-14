# KICKOFF PROMPT — Leakproof, Experiment 0 (Foundation), Days 1–2

**To:** Claude Code (Opus) — builder
**From:** Samuel (operator) + Cowork strategist
**Date:** 2026-10-14. Hard deadline for the whole project: **Fri Oct 30, 2026, 12:00 PM CDT** (Devpost submission). Target submit: Oct 29.
**Repo:** `C:\Users\<user>\Documents\nebius-hackathon` on sam-mega-pc — from WSL2 that is `/mnt/c/Users/<user>/Documents/nebius-hackathon`. Public GitHub remote already exists (Samuel pushes the scaffold). MIT license. Product name: **Leakproof**.

**Where to run:** run Claude Code from **WSL2 Ubuntu** with the repo at the `/mnt/c/...` path. All heavy Linux work (sanitizer builds, Valgrind, fuzzing, ARVO images) happens inside Docker containers via the `Runner` abstraction, so the Windows-hosted checkout is fine; what must be Linux-side on the host is only the Nebius CLI, bash scripts, and `uv`. Keep `uv`'s cache and any large downloads (Juliet zip, ARVO images) on the Linux side (`~/.cache`, Docker's storage) — not under `/mnt/c` — to avoid slow cross-filesystem I/O. Scripts are bash + Python; `.gitattributes` forces LF.

Read `CLAUDE.md`, then `docs/research/HACKATHON_RESEARCH_BRIEF_2026-10-13.md` and `docs/research/IDEA_A_REFINED_2026-10-14.md` first. They contain the competition rules, judging criteria, platform facts, and the product decision. This prompt scopes only Experiment 0.

---

## 0. What Leakproof is (one paragraph)

An autonomous agent that takes a real C/C++ (and CUDA) repository plus a sanitizer finding (ASan/LSan/UBSan report, Valgrind/heaptrack report, or NVIDIA `compute-sanitizer` report), reproduces it, has **Nemotron 3 Ultra** (via Nebius Token Factory) root-cause and rank repair hypotheses, fans out parallel **Nemotron 3.5 Lightning** workers that implement each hypothesis in branched **Nebius Sandboxes** from one checkpoint, and runs every candidate through an **evidence gate the workers cannot see or modify** (sanitizer-clean on the reproducer, project tests, differential output on benign inputs, short re-fuzz, safe-fix check, diff-scope check, trajectory audit as flag-only). Survivors become a PR carrying before/after sanitizer logs, the rejection funnel, and the cost ledger. CUDA cases run their gate inside **Nebius Serverless Jobs** (L40S) with `compute-sanitizer`. A hosted dashboard shows every run. Tagline: *"Verified fixes, or nothing."*

Judging (25% each): Technological Implementation (incl. how well we use Token Factory/AI Cloud + Nemotron), Design (complete product), Potential Impact, Quality of Idea. Judges may judge from README + 3-min video alone.

## 1. Hard rules for the whole project

1. **Clean room.** Nothing — no code, configs, prompts, scripts, or file layouts — from Samuel's employer's harness. Build from public knowledge only.
2. **No secrets in the repo.** `.env` (gitignored) + `.env.example`. Never print keys in logs or reports. Pre-commit hook or CI check that greps for `NEBIUS_API_KEY=` values / long tokens.
3. **Every model call is metered.** Append to `runs/cost_ledger.jsonl` (model, prompt/completion/reasoning tokens, computed $ from the price table, purpose, run id). A **budget guard** hard-stops the process at a configurable cap (`LEAKPROOF_BUDGET_USD`, default 2.00 for E0). Token Factory has no spend cap and returns 402 when the balance is gone.
4. **Record platform feedback as you go** in `docs/FEEDBACK.md` (per tool: what used for, what worked, what needs work, zero-to-hello-world experience, would build again). This is a mandatory submission section and a $100×10 prize; be specific and measured (exact error strings, timings, doc gaps).
5. **Decisions go in `docs/DECISIONS.md`** (numbered, dated). **Questions for Samuel go in `docs/HUMAN.md`** as `## QUESTION NNNN` blocks; he answers with `## ANSWER NNNN`. Do not block on a question if a reasonable default exists — take the default, note it, continue.
6. **E0 spend cap: $5 total** (Token Factory + AI Cloud). Any single action that would cost > $2 → ask first.
7. Keep E0 inside its scope (section 3). The agent loop (planner/workers/gate) is **E1**, not E0 — except the small "hello fix" stretch at the end.
8. Python 3.12 + `uv`; `ruff` + `pytest`; type hints; small modules; no framework lock-in (plain `openai` SDK against Token Factory; no LangChain for the core loop).

## 2. Environment facts (verified 2026-10-13/14)

- **Token Factory**: OpenAI-compatible, base URL `https://api.tokenfactory.nebius.com/v1/`, Bearer `NEBIUS_API_KEY`. NVIDIA models and $/M tokens (in/out):
  - `nvidia/Nemotron-3-Ultra-550b-a55b` — 1M ctx — 1.00 / 3.00 — planner/root-cause
  - `nvidia/Nemotron-3_5-Lightning` — 1M ctx — 0.06 / 0.24 — patch workers (SWE-bench Verified ~51.6)
  - `nvidia/nemotron-3-super-120b-a12b` — 256K ctx — 0.30 / 0.90 — alternative planner (showed `status: error` in the catalog JSON on Oct 13; have a fallback)
  - `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` — 262K ctx — 0.06 / 0.24 — triage/classification
  - Reasoning is ON by default. Toggle (undocumented by Nebius, documented by NVIDIA): `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`; Token Factory also exposes top-level `reasoning_effort` (`none|minimal|low|medium|high|xhigh|max`) — test which works. Reasoning may come back as `message.reasoning_content` or `reasoning`. `response_format: json_schema` is not tagged as supported for Nemotron — test; always also put the schema in the prompt and validate + repair-retry. Tool calling: OpenAI format; `parallel_tool_calls` only in the Responses API schema — test on chat completions. Rate limits dynamic (~60 RPM / 400K TPM baseline, 429 + `Retry-After`, `x-ratelimit-*` headers). Batch API: `/v1/batches`, JSONL, 50% off, 24h window — Nemotron batchability untested. Usage returns `completion_tokens_details.reasoning_tokens`; no cost field → compute locally.
- **Sandboxes (Contree, beta, free during beta)**: REST base `https://api.tokenfactory.nebius.com/sandboxes/v1`, headers `Authorization: Bearer $NEBIUS_API_KEY` **and** `Project: $NEBIUS_PROJECT_ID`. SDK `contree-sdk==0.3.6` (pin it; API is churning), CLI `contree-cli` (uses `NEBIUS_AI_PROJECT`), MCP `contree-mcp`. Any OCI image importable (`contree images import nvidia/cuda:12.6.3-devel-ubuntu22.04`); ENTRYPOINT/CMD/WORKDIR dropped; image ENV applied only with `shell=true`. **No GPU.** Every non-disposable run saves the post-run filesystem as a new immutable image UUID → branch N runs from one UUID. SDK `run()` defaults `disposable=True` (discard); pass `disposable=False` to keep. `networking.enabled=false` boots with no NIC. Limits: `GET /v1/whoami` (expect ~10 concurrent, 50 ceiling; timeout cap ~3600 s); stdout/stderr capture 1 MiB default / 10 MiB max → write big logs to files and download from the saved image. vCPU/RAM/disk unpublished → measure with `nproc`, `free -g`, `df -h`. Spawn ~0.4–5 s. **Access may not be approved yet when you start** → the Runner abstraction (section 3.3) must make local Docker and Contree interchangeable.
- **Nebius AI Cloud Serverless Jobs**: CLI `curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash`; `nebius profile create --endpoint api.nebius.cloud --federation-endpoint auth.nebius.com --parent-id <project_id>` (browser auth). Quickstart job:
  ```bash
  nebius ai job create --name lp-smoke --image nvidia/cuda:12.6.3-devel-ubuntu22.04 \
    --container-command bash --args "/run.sh" --inject-file run.sh:/run.sh \
    --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --preemptible --follows-spot-price --timeout 1h
  nebius ai job get-by-name --name lp-smoke ; nebius ai job logs <id> --follow ; nebius ai job delete <id>
  ```
  Preemptible L40S ≈ $0.75/hr all-in (eu-north1); startup "several minutes" (bills during STARTING; cancel if STARTING > 10 min); `--args` splits on spaces → put the driver script in an injected file (≤ 64 KiB) or the image; results via `--volume s3://<bucket>:/out:rw`; logs CLI/console only. No `--privileged` → `ncu` probably fails (`ERR_NVGPUCTRPERM`); `compute-sanitizer` needs no privileges. Quotas: check eu-north1 L40S + preemptible VMs; **non-GPU vCPU quota is 0 in eu-north1 by default**.
- **Local box**: Windows 11 + WSL2 Ubuntu + Docker Desktop (WSL integration) + RTX 5090 (sm_120). CUDA toolkit installed inside WSL2 (Windows driver only; never install a Linux driver in WSL). `compute-sanitizer` works on WSL2. Docker GPU: `docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu22.04 nvidia-smi`.
- **Datasets**: Juliet 1.3 C/C++ (NIST SARD suite 112, public domain) — each test case has `bad()` and `good*()`; compile with `-DINCLUDEMAIN -DOMITGOOD` for bad-only binaries. ARVO (Docker-reproducible OSS-Fuzz memory bugs; verify exact image naming from https://github.com/n132/ARVO-Meta README before pulling; reproducer command inside the image is `arvo`). AutoPatchBench-Lite (113, in meta-llama/PurpleLlama) and PATCHBENCH for later.

## 3. E0 deliverables (in order; commit after each)

### 3.1 Repo skeleton
Already present from the scaffold: `CLAUDE.md`, `LICENSE` (MIT), `README.md` with the final section headings, `.env.example`, `.gitignore`, `.gitattributes`, `docs/{DECISIONS,HUMAN,FEEDBACK,ARVO_NOTES}.md`, `docs/research/`, `docs/kickoff/`, `runs/README.md`. You add: `pyproject.toml` (uv, Python 3.12, `ruff`, `pytest`), the `leakproof/` package, `scripts/`, `images/`, `cases/`, `tests/`, and GitHub Actions CI (ruff + pytest, unit tests only, no secrets). Append to DECISIONS.md as you decide things; never rewrite earlier entries.

### 3.2 `leakproof/llm/` — Token Factory client + smoke tests
- `models.py`: registry with IDs, context, prices, role defaults.
- `client.py`: thin wrapper over `openai` (base_url from env): retries/backoff on 429/5xx/529 honoring `Retry-After`; per-call usage → `runs/cost_ledger.jsonl`; budget guard; `think(on/off, effort)` helper that tries `chat_template_kwargs` then `reasoning_effort` and records which worked; `structured(schema)` helper = json_schema if accepted else prompt-embedded schema, with validation + one repair retry; `tools()` helper.
- `scripts/smoke_tf.py`: for Ultra, Lightning, Nano (Super if up): hello call; thinking off/on with token counts and latency; `reasoning_content` field name; json_schema honored? parallel tool calls on a two-tool prompt? 20 concurrent Lightning calls → print `x-ratelimit-*` headers and any 429s; 2-line Batch job on Lightning (accepted? completion time?). Write results to `docs/FEEDBACK.md` under "Token Factory". **Cap: $0.50.**

### 3.3 `leakproof/runner/` — one interface, two backends
```python
class Runner(Protocol):
    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef
    def run(self, image: ImageRef, cmd: list[str] | str, *, files: dict[str, bytes|Path] = {}, env: dict = {}, cwd: str = "/work", timeout_s: int = 600, network: bool = True, save: bool = False) -> RunResult   # RunResult: exit_code, stdout, stderr, image (if saved), elapsed_s, max_rss_kb, cost
    def download(self, image: ImageRef, guest_path: str, local: Path) -> None
    def read(self, image: ImageRef, guest_path: str) -> bytes
```
- `LocalDockerRunner`: `docker build`; `docker run` (with `--network none` when `network=False`, `--memory`/`--cpus` limits, `--cap-add SYS_PTRACE` only if LSan needs it — test); `save=True` → `docker commit` to a content-named tag; branching = run N containers from the same image tag.
- `ContreeRunner`: `contree-sdk` 0.3.6; `images.oci()`/`build` → UUID; `run(..., disposable=not save)`; `networking.enabled=network`; downloads via saved image. Integration tests auto-skip when `GET /v1/whoami` is 403 (not approved yet) and say so.
- Unit tests for the interface contract run against `LocalDockerRunner` with `ubuntu:22.04`.
- Base images (Dockerfiles in `images/`): `cpp-sanitizers` (ubuntu 22.04 + clang-18/gcc-13 + cmake + ninja + valgrind + heaptrack + libfuzzer/AFL++ + python3) and `cuda-dev` (`nvidia/cuda:12.6.3-devel-ubuntu22.04` + cmake). Build both locally; try importing `cuda-dev` into Contree if access exists (time it; note size).

### 3.4 `leakproof/findings/` — sanitizer report parsers → canonical Finding
Parse ASan/LSan/UBSan (and, stub, `compute-sanitizer` memcheck/leak-check) text into `Finding{tool, kind (leak|heap-buffer-overflow|use-after-free|double-free|null-deref|uninit|…), cwe_guess, frames[], alloc_site, free_site, raw}`. Fixture logs in `tests/fixtures/`. 100% of Juliet reports from 3.5 must parse.

### 3.5 Juliet smoke set (harness unit tests, not the headline)
`scripts/juliet_fetch.py` downloads SARD suite 112; `scripts/juliet_select.py` picks ~60 cases: 30 × CWE-401, 15 × CWE-415, 15 × CWE-416 (varied control-flow variants, both C and C++). For each: build bad-only with `clang -fsanitize=address,undefined -g -O1 -DINCLUDEMAIN -DOMITGOOD` (+ `testcasesupport`), run, capture the report, parse → `cases/juliet/<id>.json` (source paths, build cmd, run cmd, expected finding kind). Also build good-only and confirm it is sanitizer-clean (this is the gate's "fixed" oracle). Output a table in `docs/REPORT_E0.md`: detected/parsed per CWE.

### 3.6 ARVO probe (3 cases)
From ARVO-Meta pick 3 small-project cases (prefer CWE-401/416/122 in small C libraries, e.g. libtiff/jq/zstd-sized or smaller). Pull the `-vul` images, run the reproducer, capture the sanitizer report, parse it, record image size, pull time, build time, and whether the fix image exists. Write `docs/ARVO_NOTES.md` (naming scheme, how to extract the harness + crash input, how to rebuild with our flags, licensing notes). Do **not** attempt fixes yet.

### 3.7 Nebius AI Cloud smoke (only after Samuel confirms the $25 top-up + quotas in HUMAN.md)
Install CLI in WSL2, create profile (Samuel does the browser login), `nebius compute platform list`, then one preemptible L40S job (command above) whose `run.sh` runs `nvidia-smi`, compiles a tiny CUDA sample with an injected out-of-bounds write (`cases/cuda/oob_global.cu`) and runs `compute-sanitizer --tool memcheck` + `--leak-check full` on a second sample with a missing `cudaFree`, then tries `ncu --metrics gpu__time_duration.sum` (expect failure; record the exact error). Time every state transition (PROVISIONING→STARTING→RUNNING→COMPLETED). Record $ (job time × $0.75/hr) in the ledger and the timings in FEEDBACK under "Serverless Jobs". **Cap: $1.** Then run the same two CUDA samples locally on the 5090 in WSL2 and inside `docker --gpus all` — record that both paths work.

### 3.8 Stretch (only if 3.1–3.7 are green): "hello fix"
On one Juliet CWE-401 case: give Lightning the source + parsed finding, ask for a unified diff (thinking off), apply in a fresh `LocalDockerRunner` run from the base image, rebuild bad-only, re-run → LSan clean AND good-only still clean. Log cost. This is a 2-hour spike to de-risk E1; no gate, no planner.

### 3.9 Report
`docs/REPORT_E0.md`: what works (with numbers: spawn times, build times, image sizes, rate-limit headers, job timings, $ spent), what doesn't, open questions for Samuel, and the recommended E1 start point. Update FEEDBACK.md and DECISIONS.md.

## 4. Gate E0 (end of Day 2) — pass criteria
- [ ] Token Factory: Ultra + Lightning + Nano calls work; thinking toggle method known; json_schema behavior known; cost ledger + budget guard proven (force a stop in a test).
- [ ] `LocalDockerRunner` passes contract tests; `ContreeRunner` passes them too **or** is blocked only by beta approval (403 on whoami), documented.
- [ ] 60 Juliet cases build, reproduce, parse (≥ 95%); good-only variants are clean.
- [ ] 3 ARVO cases reproduce and parse; ARVO_NOTES written.
- [ ] One Serverless L40S job completed with compute-sanitizer output; timings + cost recorded (or blocked by quota/billing, documented).
- [ ] Total E0 spend ≤ $5 and visible in `runs/cost_ledger.jsonl`.

## 5. Roadmap after E0 (for orientation only)
E1 (Days 3–5): intake/repro → Ultra planner (hypotheses as JSON) → N Lightning workers in branched runs → first end-to-end fixes on Juliet then 5 ARVO cases. E2 (Days 6–8): the 8-check evidence gate, rejection reasons, funnel, PR generator; ARVO to 20–30 cases. E3 (Days 9–10): CUDA path on Serverless Jobs (batched). E4 (Days 11–12): dashboard (static SPA + run JSON), budget-guarded demo button, Batch-API model leaderboard. E5 (Days 13–14): full ARVO eval (40–60), 2–3 live PRs on open OSS-Fuzz bugs, stretch modes only if green. E6 (Days 15–16): README numbers, architecture diagram, feedback, video, Devpost draft. Submit Oct 29.

## 6. Operator status at kickoff (2026-10-14)
Done by Samuel: Token Factory account + credit; API key + project ID (in `.env`, never in chat); Sandboxes beta **requested** (not yet approved — expect 403 on `/whoami`); Builders Program applied (pending); Tavily account; Nebius AI Cloud account (card/top-up status → confirm in HUMAN.md before 3.7); GitHub remote created and scaffold pushed. Local: Windows 11 + WSL2 Ubuntu + Docker Desktop. If the CUDA toolkit is not yet installed inside WSL2, do the 5090 checks of 3.7 inside `docker run --gpus all nvidia/cuda:12.6.3-devel-ubuntu22.04` instead and note it.
