# Leakproof — project rules for Claude Code

**What this is:** Samuel's entry in the Nebius x NVIDIA Global AI Hackathon (Devpost). Deadline **Fri Oct 30, 2026, 12:00 PM CDT**; target submit Oct 29. Track: Coding & Agentic Engineering. Product: an autonomous agent that fixes memory defects in C/C++ (and CUDA) with machine-verified evidence — "Verified fixes, or nothing."

**Start here, in order:** `docs/research/HACKATHON_RESEARCH_BRIEF_2026-10-13.md` → `docs/research/IDEA_A_REFINED_2026-10-14.md` → the current kickoff prompt in `docs/kickoff/` (highest-numbered experiment). The kickoff prompt scopes the work; do not exceed it.

## Non-negotiables
1. **Clean room.** Public knowledge and our own code only.
2. **No secrets in the repo or in logs.** Keys live in `.env` (gitignored). `.env.example` lists names only. Never echo a key. A pre-commit/CI check must fail on leaked tokens.
3. **Every model call is metered.** Append to `runs/cost_ledger.jsonl`; respect `LEAKPROOF_BUDGET_USD` (hard stop). Token Factory has no spend cap (402 when empty).
4. **Spend caps per experiment** are in the kickoff prompt. Any single action > $2 → ask first in `docs/HUMAN.md`.
5. **Record platform feedback as you go** in `docs/FEEDBACK.md` (per tool: used for / worked / needs work / zero-to-hello-world / would build again). Exact error strings, timings, doc gaps. This is a mandatory submission section.
6. **Decisions → `docs/DECISIONS.md`** (append-only, numbered `D-NNNN`, dated). **Questions → `docs/HUMAN.md`** (`## QUESTION NNNN`; Samuel answers with `## ANSWER NNNN`). Take a sensible default and continue rather than block, unless the question is about money, licensing, or anything irreversible.
7. **Workers never see the gate.** Any code path that proposes patches must not be able to read or modify tests, harness, build flags, or benchmark inputs used for verification.
8. **Honest numbers.** Report raw vs verified side by side. Never present a "silenced" sanitizer as a verified fix.

## Environment
- Checkout: `C:\Users\<user>\Documents\nebius-hackathon` = `/mnt/c/Users/<user>/Documents/nebius-hackathon` in WSL2. Run Claude Code from WSL2 Ubuntu. Docker Desktop (WSL integration) provides `docker`; `--gpus all` works for the RTX 5090.
- Keep caches and large downloads on the Linux side (`~/.cache`, Docker storage), not under `/mnt/c`.
- Python 3.12 + `uv`; `ruff` + `pytest`; type hints; plain `openai` SDK against Token Factory (base URL `https://api.tokenfactory.nebius.com/v1/`); no heavy agent frameworks in the core loop.
- Env vars: `NEBIUS_API_KEY`, `NEBIUS_PROJECT_ID` (SDK/REST) and `NEBIUS_AI_PROJECT` (contree CLI/MCP — same value), `TAVILY_API_KEY` (optional), `LEAKPROOF_BUDGET_USD`.
- Models (Token Factory IDs): planner `nvidia/Nemotron-3-Ultra-550b-a55b`; workers `nvidia/Nemotron-3_5-Lightning`; triage `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`; alt planner `nvidia/nemotron-3-super-120b-a12b`.
- Sandboxes (Contree) may still be unapproved: `GET https://api.tokenfactory.nebius.com/sandboxes/v1/whoami` with `Authorization: Bearer` + `Project:` headers → 403 means not yet. The `Runner` abstraction must keep local Docker and Contree interchangeable.

## Conventions
- Commits: small, imperative, one concern each. Commit after each kickoff deliverable.
- Line endings LF (`.gitattributes`); shell scripts `#!/usr/bin/env bash` + `set -euo pipefail`.
- Experiment reports: `docs/REPORT_E<N>.md` with measured numbers (times, sizes, $, pass rates) and open issues.
- Do not rewrite history; do not force-push.
