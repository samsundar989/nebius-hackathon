# Leakproof in CI (template)

`leakproof-fix.yml` runs after your fuzzing workflow fails. It takes the first crash input from that run's artifact, runs `leakproof fix` on your project's `leakproof.toml`, and uploads the evidence bundle. When a fix is verified, the bundle contains the diff and every gate check. When no fix is verified, the bundle says why. The workflow never pushes code or opens a pull request: a person reviews the diff.

Setup:

1. Add a `leakproof.toml` to your repository (see [examples/csvsplit](../csvsplit/leakproof.toml)).
2. Make your fuzzing workflow upload its crash inputs as an artifact named `crashes`, and set `workflows: ["fuzz"]` to that workflow's name.
3. Add the repository secret `NEBIUS_API_KEY` and the repository variable `NEBIUS_PROJECT_ID`.
4. Copy `leakproof-fix.yml` to `.github/workflows/`.

Each run is capped at `LEAKPROOF_BUDGET_USD` of model spend ($0.50 in the template). The csvsplit demo cost $0.01 per fix. The gate runs in Docker on the runner with networking off.

Status: this template has not run on GitHub yet; we have no demo repository with the secret. It runs the same `leakproof fix` and `render_bundle.py` commands as `scripts/demo_run.sh` (steps 3 and 1). They were last run end to end on 2026-10-24 (`runs/p5_byo_csvsplit`: verified, $0.0100, 130 s).
