$TradeV2Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$TradeV2StateDir = Join-Path $TradeV2Root 'runtime/operator'
$TradeV2StateFile = Join-Path $TradeV2StateDir 'local-workstation.json'
$TradeV2ApiUrl = 'http://127.0.0.1:8000/api/v1/health'
$TradeV2UiUrl = 'http://127.0.0.1:5173/'

function Get-TradeV2OwnedProcess {
    param([Parameter(Mandatory)]$Record)
    try {
        $process = Get-Process -Id ([int]$Record.pid) -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -ne [long]$Record.start_ticks) {
            return $null
        }
        return $process
    } catch {
        return $null
    }
}

function Get-TradeV2Health {
    try {
        $response = Invoke-RestMethod -Uri $TradeV2ApiUrl -TimeoutSec 2 -ErrorAction Stop
        return $response.status -eq 'AVAILABLE' -and $response.live -eq 'LIVE_DISABLED'
    } catch {
        return $false
    }
}

function Get-TradeV2UiHealth {
    try {
        $response = Invoke-WebRequest -Uri $TradeV2UiUrl -TimeoutSec 2 -ErrorAction Stop
        return $response.StatusCode -eq 200 -and $response.Content -match 'Trade v2'
    } catch {
        return $false
    }
}

function Get-TradeV2State {
    if (-not (Test-Path -LiteralPath $TradeV2StateFile -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $TradeV2StateFile -Raw | ConvertFrom-Json
    } catch {
        throw "Operator state is unreadable: $TradeV2StateFile"
    }
}
