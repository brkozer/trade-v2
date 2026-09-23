<#
Finite public-only OI continuation. Each collector invocation verifies every
prior chunk and writes only the exact next timestamps. A failed collection is
never silently replaced with zeros or an overlapping backfill.
#>
param(
    [ValidateRange(1, 1344)][int]$Rounds = 1344,
    [ValidateRange(300, 3600)][int]$IntervalSeconds = 1800,
    [ValidateRange(20, 1000)][int]$MinFreeGB = 100
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$collector = Join-Path $root 'ops\collect_forward_oi.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $collector -PathType Leaf)) {
    throw 'Target-local public OI collector is missing'
}
$firstChunk = Get-ChildItem -LiteralPath (Join-Path $root 'data\public') -Directory |
    Where-Object { $_.Name -like 'prospective_oi_*' } |
    Sort-Object Name |
    Select-Object -First 1
if ($null -eq $firstChunk) { throw 'A verified first OI chunk is required' }

$campaign = Join-Path $root ('runtime\recorder\oi-continuation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $campaign -ErrorAction Stop | Out-Null
$statusPath = Join-Path $campaign 'status.json'
$metadata = [ordered]@{
    started_utc = [DateTime]::UtcNow.ToString('o')
    first_chunk = $firstChunk.Name
    requested_rounds = $Rounds
    interval_seconds = $IntervalSeconds
    min_free_gb = $MinFreeGB
    status = 'WAITING_FOR_INTERVAL'
    successful_rounds = 0
    failed_rounds = 0
    consecutive_failures = 0
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

Push-Location -LiteralPath $root
try {
    for ($index = 1; $index -le $Rounds; $index++) {
        Start-Sleep -Seconds $IntervalSeconds
        if (Test-Path -LiteralPath (Join-Path $campaign 'stop.request')) {
            $metadata.status = 'STOP_REQUESTED'
            break
        }
        $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($root))
        if ($drive.AvailableFreeSpace -lt $MinFreeGB * 1GB) {
            throw "Free disk below $MinFreeGB GB before OI round $index"
        }
        $metadata.status = 'COLLECTING'
        $log = Join-Path $campaign ('round-{0:D4}.log' -f $index)
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $python $collector *> $log
            $collectorExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($collectorExitCode -eq 0) {
            $metadata.successful_rounds++
            $metadata.consecutive_failures = 0
        } else {
            $metadata.failed_rounds++
            $metadata.consecutive_failures = 1 + [int]$metadata.consecutive_failures
            if ($metadata.consecutive_failures -ge 3) {
                throw "Three consecutive OI collection failures; see $log"
            }
        }
        $metadata.last_round_utc = [DateTime]::UtcNow.ToString('o')
        $metadata.status = 'WAITING_FOR_INTERVAL'
        $metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    }
    if ($metadata.status -eq 'WAITING_FOR_INTERVAL') { $metadata.status = 'COMPLETE' }
} catch {
    $metadata.status = 'FAILED'
    $metadata.error = $_.Exception.Message
    throw
} finally {
    $metadata.finished_utc = [DateTime]::UtcNow.ToString('o')
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    Pop-Location
}
