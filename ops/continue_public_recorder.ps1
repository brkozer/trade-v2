<#
Run a finite, public-only prospective recorder campaign after an existing run.
The existing recorder owns journal integrity and closed-run read-back acceptance.
All output remains under Trade v2/runtime; no authenticated transport is used.
#>
param(
    [Parameter(Mandatory = $true)][int]$WaitPid,
    [ValidateRange(1, 48)][int]$Sessions = 24,
    [ValidateRange(1, 3600)][int]$Seconds = 1800,
    [ValidateRange(20, 1000)][int]$MinFreeGB = 100
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Target-local Python environment is missing'
}

$prior = Get-CimInstance Win32_Process -Filter "ProcessId=$WaitPid"
if ($null -eq $prior -or $prior.CommandLine -notmatch 'tradev2\.cli record-public --symbols BTCUSDT ETHUSDT') {
    throw 'WaitPid is not the expected active BTCUSDT/ETHUSDT public recorder'
}

$campaign = Join-Path $root ('runtime\recorder\continuation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $campaign -ErrorAction Stop | Out-Null
$metadata = [ordered]@{
    prior_pid = $WaitPid
    prior_command = $prior.CommandLine
    started_utc = [DateTime]::UtcNow.ToString('o')
    requested_sessions = $Sessions
    session_seconds = $Seconds
    min_free_gb = $MinFreeGB
    status = 'WAITING_FOR_PRIOR_RUN'
    completed_sessions = 0
}
$statusPath = Join-Path $campaign 'status.json'
$metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

Push-Location -LiteralPath $root
try {
    Wait-Process -Id $WaitPid -Timeout 2700 -ErrorAction Stop
    $metadata.status = 'COLLECTING'
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    for ($index = 1; $index -le $Sessions; $index++) {
        if (Test-Path -LiteralPath (Join-Path $campaign 'stop.request')) {
            $metadata.status = 'STOP_REQUESTED'
            break
        }
        $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($root))
        if ($drive.AvailableFreeSpace -lt $MinFreeGB * 1GB) {
            throw "Free disk below $MinFreeGB GB before session $index"
        }
        $log = Join-Path $campaign ('session-{0:D2}.log' -f $index)
        & $python -m tradev2.cli record-public --symbols BTCUSDT ETHUSDT --seconds $Seconds *> $log
        if ($LASTEXITCODE -ne 0) {
            throw "Public recorder failed in session $index; see $log"
        }
        $metadata.completed_sessions = $index
        $metadata.last_closed_utc = [DateTime]::UtcNow.ToString('o')
        $metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    }
    if ($metadata.status -eq 'COLLECTING') { $metadata.status = 'COMPLETE' }
} catch {
    $metadata.status = 'FAILED'
    $metadata.error = $_.Exception.Message
    throw
} finally {
    $metadata.finished_utc = [DateTime]::UtcNow.ToString('o')
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    Pop-Location
}
