# Build the demo service image and smoke-test it (before asking Samuel to apply render.yaml).
# Run through workerq: powershell -File scripts/with_docker.ps1 powershell -File scripts/service_smoke.ps1
$ErrorActionPreference = "Stop"
$name = "lpdemo-smoke"
docker build -q -t leakproof-demo:smoke -f service/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Output "BUILD FAILED"; exit 1 }
docker rm -f $name 2>$null | Out-Null
docker run -d --name $name -p 18080:10000 -e PORT=10000 -e DEMO_ENABLED=false leakproof-demo:smoke | Out-Null
$ok = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 1
    try { $h = Invoke-RestMethod -Uri "http://127.0.0.1:18080/healthz" -TimeoutSec 3; $ok = $true; break } catch {}
}
if (-not $ok) { docker logs $name; docker rm -f $name | Out-Null; Write-Output "HEALTHZ FAILED"; exit 1 }
Write-Output ("healthz: " + ($h | ConvertTo-Json -Compress))
$r = Invoke-RestMethod -Uri "http://127.0.0.1:18080/run" -Method Post -TimeoutSec 10
Write-Output ("run: verdict=" + $r.verdict + " recorded=" + $r.recorded + " reason=" + $r.reason + " case=" + $r.case)
docker rm -f $name | Out-Null
docker rmi leakproof-demo:smoke | Out-Null
if ($r.recorded -ne $true) { exit 1 }
Write-Output "SMOKE OK"
