# Build the demo service image and smoke-test it (before asking Samuel to apply render.yaml).
# Run through workerq: powershell -File scripts/with_docker.ps1 powershell -File scripts/service_smoke.ps1 [-Live]
# -Live: DEMO_ENABLED=true with the local .env (docker reads it; nothing is printed): one real
# Juliet case through the sandboxed local runner, ~$0.02.
param([switch]$Live, [int]$Runs = 1)
$ErrorActionPreference = "Stop"
$name = "lpdemo-smoke"
docker build -q -t leakproof-demo:smoke -f service/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Output "BUILD FAILED"; exit 1 }
docker rm -f $name 2>$null | Out-Null
$runArgs = @("run", "-d", "--name", $name, "-p", "18080:10000", "-e", "PORT=10000")
if ($Live) {
    $envFile = "C:\Users\<user>\Documents\nebius-hackathon\.env"
    $runArgs += @("--env-file", $envFile, "-e", "DEMO_ENABLED=true", "-e", "LEAKPROOF_BUDGET_USD=0.10")
} else {
    $runArgs += @("-e", "DEMO_ENABLED=false")
}
docker @runArgs leakproof-demo:smoke | Out-Null
$ok = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 1
    try { $h = Invoke-RestMethod -Uri "http://127.0.0.1:18080/healthz" -TimeoutSec 3; $ok = $true; break } catch {}
}
if (-not $ok) { docker logs $name; docker rm -f $name | Out-Null; Write-Output "HEALTHZ FAILED"; exit 1 }
Write-Output ("healthz: " + ($h | ConvertTo-Json -Compress))
foreach ($k in 1..$Runs) {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:18080/run" -Method Post -TimeoutSec 600
    Write-Output ("run ${k}: verdict=" + $r.verdict + " recorded=" + $r.recorded + " reason=" + $r.reason + " case=" + $r.case + " usd=" + $r.usd + " s=" + $r.elapsed_s + " workers=" + (($r.workers | ForEach-Object { $_.verdict }) -join ","))
    Start-Sleep -Seconds 2
}
if ($Live) {
    # The candidate code must not see the key: no NEBIUS variable in a nobody-run shell.
    $probe = docker exec $name setpriv --reuid=nobody --regid=nogroup --clear-groups -- env -i /bin/sh -c "cat /proc/1/environ 2>&1 | tr '\0' '\n' | grep -c NEBIUS_API_KEY || true"
    Write-Output ("nobody can read the server's key from /proc/1/environ: " + ($probe -ne "0" -and $probe -notmatch "denied"))
    $ErrorActionPreference = "Continue"
    docker logs --tail 5 $name 2>&1 | ForEach-Object { "$_" }
}
docker rm -f $name | Out-Null
docker rmi leakproof-demo:smoke | Out-Null
if ($Live) {
    if ($r.recorded -eq $true) { Write-Output "LIVE RUN FELL BACK TO RECORDED"; exit 1 }
} elseif ($r.recorded -ne $true) { exit 1 }
Write-Output "SMOKE OK"
