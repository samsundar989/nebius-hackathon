# Leakproof

**Verified fixes, or nothing.** An autonomous agent that fixes memory defects in C/C++ and CUDA code — leaks, use-after-free, double free, buffer overflows — and ships every fix with machine-verified evidence: sanitizer-clean reproduction, passing tests, identical output on benign inputs, a short re-fuzz, and a safe-fix check. Powered by NVIDIA Nemotron 3 on Nebius Token Factory, Nebius Sandboxes, and Nebius AI Cloud Serverless Jobs.

> Built for the Nebius x NVIDIA Global AI Hackathon (Oct 2026). Status: Experiment 0 (foundation) in progress.

## What it is

_(problem, audience, one-paragraph description — filled in E6)_

## How it works

_(architecture diagram; intake → reproduce → plan → branch → gate → deliver)_

## How we use NVIDIA Nemotron

_(which model does what and why, with measured cost per verified fix: Ultra planner/root-cause, 3.5 Lightning workers, Nano triage)_

## How we use Nebius Token Factory, Sandboxes, and AI Cloud

_(Token Factory inference + Batch API; Sandboxes checkpoint-and-branch per hypothesis with networking off for the gate; Serverless L40S jobs running NVIDIA compute-sanitizer for CUDA cases)_

## Results

_(Juliet smoke set; ARVO sample: built / silenced / verified per CWE and per model; CUDA set; live PRs; raw-vs-verified funnel)_

## The evidence gate

_(the eight checks, what each rejects, and the sources they are borrowed from)_

## Setup

_(prerequisites, env vars, `uv sync`, how to run one case locally, how to run with Sandboxes/Serverless)_

## Cost ledger

_(total spend by component, including failed runs)_

## Feedback on Nebius and NVIDIA tools

_(see docs/FEEDBACK.md — summarized here for the submission)_

## Limitations

_(what it does not do yet; honest failure modes)_

## License

MIT — see [LICENSE](LICENSE).
