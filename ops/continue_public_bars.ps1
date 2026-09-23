<#
Finite public-only 20-symbol candle collection alongside the L2 recorder.
Every cycle extends the immutable contiguous prospective chain. Failures remain
in target-local logs; repeated failure stops the helper for human review.
#>
param(
    [int]$WaitPid = 0,
    [int]$WaitCampaignPid = 0,
    [switch]$ResumeExistingChain,
    [string]$PriorStatusPath,
    [ValidateRange(1, 1344)][int]$Rounds = 24,
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
$isCampaignHandoff = $WaitCampaignPid -gt 0
$modeCount = [int]($WaitPid -gt 0) + [int]$isCampaignHandoff +
    [int]($ResumeExistingChain.IsPresent)
if ($modeCount -ne 1) {
    throw 'Specify exactly one active-recorder WaitPid, bar-campaign WaitCampaignPid, or ResumeExistingChain'
}
$waitTargetPid = if ($isCampaignHandoff) { $WaitCampaignPid } else { $WaitPid }
$prior = $null
if (-not $ResumeExistingChain) {
    $prior = Get-CimInstance Win32_Process -Filter "ProcessId=$waitTargetPid"
    if ($null -eq $prior) { throw 'Wait target process is not active' }
}
$resolvedPriorStatus = $null
if ($isCampaignHandoff) {
    if ([string]::IsNullOrWhiteSpace($PriorStatusPath)) {
        throw 'Bar-campaign handoff requires PriorStatusPath'
    }
    $resolvedPriorStatus = (Resolve-Path -LiteralPath $PriorStatusPath).Path
    $recorderRoot = Join-Path $root 'runtime\recorder'
    if (-not $resolvedPriorStatus.StartsWith($recorderRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $resolvedPriorStatus) -ne 'status.json' -or
        (Split-Path -Leaf (Split-Path -Parent $resolvedPriorStatus)) -notlike 'bars-continuation-*') {
        throw 'Prior status is not a target-local bar campaign'
    }
    $priorMetadata = Get-Content -LiteralPath $resolvedPriorStatus -Raw | ConvertFrom-Json
    $expectedScript = Join-Path $PSScriptRoot 'continue_public_bars.ps1'
    if (-not $prior.CommandLine.Contains($expectedScript) -or
        -not $prior.CommandLine.Contains("-WaitPid $($priorMetadata.prior_pid)") -or
        $priorMetadata.status -ne 'COLLECTING') {
        throw 'WaitCampaignPid or prior bar-campaign status does not match active collection'
    }
} elseif (-not $ResumeExistingChain -and
          $prior.CommandLine -notmatch 'tradev2\.cli record-public --symbols BTCUSDT ETHUSDT') {
    throw 'WaitPid is not the expected active public recorder'
}
$campaign = Join-Path $root ('runtime\recorder\bars-continuation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $campaign -ErrorAction Stop | Out-Null
$statusPath = Join-Path $campaign 'status.json'
$metadata = [ordered]@{
    prior_pid = $waitTargetPid
    prior_status_path = $resolvedPriorStatus
    resume_existing_chain = $ResumeExistingChain.IsPresent
    started_utc = [DateTime]::UtcNow.ToString('o')
    requested_rounds = $Rounds
    interval_seconds = $IntervalSeconds
    min_free_gb = $MinFreeGB
    status = if ($ResumeExistingChain) { 'COLLECTING' } else { 'WAITING_FOR_PRIOR_RUN' }
    successful_rounds = 0
    failed_rounds = 0
    consecutive_failures = 0
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

Push-Location -LiteralPath $root
try {
    if (-not $ResumeExistingChain) {
        $waitMilliseconds = if ($isCampaignHandoff) { 43200000 } else { 2700000 }
        $waitHandle = [System.Diagnostics.Process]::GetProcessById($waitTargetPid)
        try {
            if (-not $waitHandle.WaitForExit($waitMilliseconds)) {
                throw 'Prior public collection did not exit within its bounded wait'
            }
        } finally {
            $waitHandle.Dispose()
        }
        if ($isCampaignHandoff) {
            $priorFinal = Get-Content -LiteralPath $resolvedPriorStatus -Raw | ConvertFrom-Json
            if ($priorFinal.status -ne 'COMPLETE' -or
                $priorFinal.successful_rounds -lt 1 -or
                $priorFinal.consecutive_failures -ne 0) {
                throw 'Prior bar campaign did not complete cleanly'
            }
        }
        $metadata.status = 'COLLECTING'
    }
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
        $savedErrorActionPreference = $ErrorActionPreference
        try {
            # Windows PowerShell surfaces native stderr as ErrorRecord objects.
            # A normal nonzero collector exit must reach the bounded retry logic.
            $ErrorActionPreference = 'Continue'
            & $python $collector *> $log
            $collectorExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        if ($collectorExitCode -eq 0) {
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
