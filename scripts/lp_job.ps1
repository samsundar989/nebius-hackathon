# Run a repo Python script with Docker available, as a workerq job on Windows.
# Uses its own venv (.venv-win): the checkout's .venv belongs to WSL and Windows uv cannot share it.
# Secrets: the snapshot workerq runs from has no .env, so point load_dotenv at the live checkout.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\lp_job.ps1 scripts\fix_batch.py --cases ...
$ErrorActionPreference = "Continue"
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
if (-not $env:LEAKPROOF_DOTENV) { $env:LEAKPROOF_DOTENV = "C:\Users\<user>\Documents\nebius-hackathon\.env" }
if (-not $env:LEAKPROOF_RUNS) { $env:LEAKPROOF_RUNS = "C:\Users\<user>\Documents\nebius-hackathon\runs" }
$env:PYTHONUNBUFFERED = "1"
& powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\with_docker.ps1" uv run --quiet python @args
exit $LASTEXITCODE
