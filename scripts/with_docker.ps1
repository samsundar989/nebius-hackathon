# Run a command with Docker Desktop available, for workerq jobs.
# Starts Docker Desktop only if it is not already running, and stops it afterwards only if this
# script started it, so idle Docker never holds RAM while a job waits in the queue.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\with_docker.ps1 docker run ...
$ErrorActionPreference = "Stop"
$started = $false
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $started = $true
    $deadline = (Get-Date).AddMinutes(4)
    do { Start-Sleep -Seconds 5; docker info *> $null } until ($LASTEXITCODE -eq 0 -or (Get-Date) -gt $deadline)
    if ($LASTEXITCODE -ne 0) { Write-Error "Docker Desktop did not start within 4 minutes" }
}
$exe, $rest = $args
& $exe @rest
$rc = $LASTEXITCODE
if ($started) { Stop-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue }
exit $rc
