# lp_job.ps1 with larger Docker limits, for a big C++ project under ASan (assimp, LibreDWG, gpac).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\lp_job_big.ps1 scripts\probe_case.py --config ...
# Submit with matching declarations: workerq submit --ram 14 --cpus 8 ...
if (-not $env:LEAKPROOF_DOCKER_CPUS) { $env:LEAKPROOF_DOCKER_CPUS = "8" }
if (-not $env:LEAKPROOF_DOCKER_MEMORY) { $env:LEAKPROOF_DOCKER_MEMORY = "12g" }
& powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\lp_job.ps1" @args
exit $LASTEXITCODE
