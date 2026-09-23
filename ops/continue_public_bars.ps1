<#
Finite public-only 20-symbol candle collection alongside the L2 recorder.
Every cycle extends the immutable contiguous prospective chain. Failures remain
in target-local logs; repeated failure stops the helper for human review.
#>
param(
    [Parameter(Mandatory = $true)][int]$WaitPid,
    [ValidateRange(1, 48)][int]$Rounds = 24,
    [ValidateRange(300, 3600)][int]$IntervalSeconds = 1800,
    [ValidateRange(20, 1000)][int]$MinFreeGB = 100
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$collector = Join-Path $root 'ops\collect_forward_bars.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $collector -PathType Leaf)) {
    throw 'Target-local public candle collector is missing'
}
$prior = Get-CimInstance Win32_Process -Filter "ProcessId=$WaitPid"
if ($null -eq $prior -or $prior.CommandLine -notmatch 'tradev2\.cli record-public --symbols BTCUSDT ETHUSDT') {
    throw 'WaitPid is not the expected active public recorder'
}
$campaign = Join-Path $root ('runtime\recorder\bars-continuation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $campaign -ErrorAction Stop | Out-Null
$statusPath = Join-Path $campaign 'status.json'
$metadata = [ordered]@{
    prior_pid = $WaitPid
    started_utc = [DateTime]::UtcNow.ToString('o')
    requested_rounds = $Rounds
    interval_seconds = $IntervalSeconds
    min_free_gb = $MinFreeGB
    status = 'WAITING_FOR_PRIOR_RUN'
    successful_rounds = 0
    failed_rounds = 0
    consecutive_failures = 0
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

Push-Location -LiteralPath $root
try {
    Wait-Process -Id $WaitPid -Timeout 2700 -ErrorAction Stop
    $metadata.status = 'COLLECTING'
    for ($index = 1; $index -le $Rounds; $index++) {
        if ($index -gt 1) { Start-Sleep -Seconds $IntervalSeconds }
        if (Test-Path -LiteralPath (Join-Path $campaign 'stop.request')) {
            $metadata.status = 'STOP_REQUESTED'
            break
        }
        $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($root))
        if ($drive.AvailableFreeSpace -lt $MinFreeGB * 1GB) {
            throw "Free disk below $MinFreeGB GB before round $index"
        }
        $log = Join-Path $campaign ('round-{0:D2}.log' -f $index)
        & $python $collector *> $log
        if ($LASTEXITCODE -eq 0) {
            $metadata.successful_rounds++
            $metadata.consecutive_failures = 0
        } else {
            $metadata.failed_rounds++
            $metadata.consecutive_failures = 1 + [int]($metadata.consecutive_failures)
            if ($metadata.consecutive_failures -ge 3) {
                throw "Three consecutive candle collection failures; see $log"
            }
        }
        $metadata.last_round_utc = [DateTime]::UtcNow.ToString('o')
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
