# One workerq job, Docker used by one process at a time: the bring-your-own demos, then the
# demo-service smoke test. Usage (from the repo root, through workerq):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/demo_chain.ps1
$ErrorActionPreference = "Continue"
$job = "$PSScriptRoot\lp_job.ps1"
Write-Output "== csvsplit: leakproof fix"
& powershell -NoProfile -ExecutionPolicy Bypass -File $job -m leakproof.cli fix --config examples/csvsplit/leakproof.toml --run-id p5_byo_csvsplit --budget 0.3
Write-Output "== csvsplit: leakproof batch"
& powershell -NoProfile -ExecutionPolicy Bypass -File $job -m leakproof.cli batch --config examples/csvsplit/leakproof.toml --findings examples/csvsplit/findings --run-id p5_batch_csvsplit --budget 0.3
Write-Output "== demo service smoke"
& powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\with_docker.ps1" powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\service_smoke.ps1"
exit 0
