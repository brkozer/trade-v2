<#
Run a finite, public-only prospective recorder campaign after an existing run.
The existing recorder owns journal integrity and closed-run read-back acceptance.
All output remains under Trade v2/runtime; no authenticated transport is used.
#>
param(
    [Parameter(Mandatory = $true)][int]$WaitPid,
    [string]$SymbolsCsv = 'BTCUSDT,ETHUSDT',
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
$symbols = @($SymbolsCsv.Split(','))
if ($symbols.Count -lt 1 -or $symbols.Count -gt 10 -or
    @($symbols | Select-Object -Unique).Count -ne $symbols.Count -or
    @($symbols | Where-Object { $_ -cnotmatch '^[A-Z0-9]+USDT$' }).Count -gt 0) {
    throw 'Expected 1..10 unique uppercase USDT symbols'
}

$prior = Get-CimInstance Win32_Process -Filter "ProcessId=$WaitPid"
$expected = 'tradev2.cli record-public --symbols ' + ($symbols -join ' ')
if ($null -eq $prior -or -not $prior.CommandLine.Contains($expected)) {
    throw 'WaitPid is not the expected active public recorder for these symbols'
}

$campaign = Join-Path $root ('runtime\recorder\continuation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $campaign -ErrorAction Stop | Out-Null
$metadata = [ordered]@{
    prior_pid = $WaitPid
    prior_command = $prior.CommandLine
    symbols = $symbols
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
        # Windows PowerShell promotes native stderr to an ErrorRecord under Stop,
        # which previously aborted on the first traceback line and lost the cause.
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $python -m tradev2.cli record-public --symbols @symbols --seconds $Seconds *> $log
            $recorderExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($recorderExitCode -ne 0) {
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
