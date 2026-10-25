# Run a repo Python script with Docker available, as a workerq job on Windows.
# Uses its own venv (.venv-win): the checkout's .venv belongs to WSL and Windows uv cannot share it.
# Secrets: the snapshot workerq runs from has no .env, so point load_dotenv at the live checkout.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\lp_job.ps1 scripts\fix_batch.py --cases ...
$ErrorActionPreference = "Continue"
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
# LEAKPROOF_HOME is the live checkout (default: Documents\nebius-hackathon under the user profile).
if (-not $env:LEAKPROOF_HOME) { $env:LEAKPROOF_HOME = Join-Path $env:USERPROFILE "Documents\nebius-hackathon" }
if (-not $env:LEAKPROOF_DOTENV) { $env:LEAKPROOF_DOTENV = Join-Path $env:LEAKPROOF_HOME ".env" }
if (-not $env:LEAKPROOF_RUNS) { $env:LEAKPROOF_RUNS = Join-Path $env:LEAKPROOF_HOME "runs" }
$env:PYTHONUNBUFFERED = "1"
& powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\with_docker.ps1" uv run --quiet python @args
exit $LASTEXITCODE
