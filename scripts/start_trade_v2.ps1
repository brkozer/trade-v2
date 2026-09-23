param([switch]$OpenBrowser)

. (Join-Path $PSScriptRoot 'workstation_common.ps1')
$ErrorActionPreference = 'Stop'
$state = Get-TradeV2State
if ($null -ne $state) {
    $api = Get-TradeV2OwnedProcess $state.api
    $ui = Get-TradeV2OwnedProcess $state.ui
    if ($null -ne $api -and $null -ne $ui -and
        (Get-TradeV2Health) -and (Get-TradeV2UiHealth)) {
        Write-Host "Trade v2 already running: $TradeV2UiUrl"
        Write-Host "API: http://127.0.0.1:8000/docs"
        if ($OpenBrowser) { Start-Process $TradeV2UiUrl }
        return
    }
    throw 'Existing launcher state is not fully healthy. Run stop_trade_v2.ps1 before restarting; no unrelated process was touched.'
}

$python = Join-Path $TradeV2Root '.venv/Scripts/python.exe'
$vite = Join-Path $TradeV2Root 'frontend/node_modules/vite/bin/vite.js'
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Missing target-local Python environment. Run the README setup commands first.'
}
if (-not $node -or -not (Test-Path -LiteralPath $vite -PathType Leaf)) {
    throw 'Missing Node or target-local frontend dependencies. Run npm ci in frontend first.'
}
New-Item -ItemType Directory -Path $TradeV2StateDir -Force | Out-Null
$apiProcess = $null
$uiProcess = $null
try {
    $apiProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'tradev2.cli', 'serve', '--port', '8000') `
        -WorkingDirectory $TradeV2Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $TradeV2StateDir 'api.stdout.log') `
        -RedirectStandardError (Join-Path $TradeV2StateDir 'api.stderr.log')
    $uiProcess = Start-Process -FilePath $node -ArgumentList @('"' + $vite + '"', '--host', '127.0.0.1', '--port', '5173', '--strictPort') `
        -WorkingDirectory (Join-Path $TradeV2Root 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $TradeV2StateDir 'ui.stdout.log') `
        -RedirectStandardError (Join-Path $TradeV2StateDir 'ui.stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($apiProcess.HasExited -or $uiProcess.HasExited) { break }
        if ((Get-TradeV2Health) -and (Get-TradeV2UiHealth)) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Startup failed. See logs under $TradeV2StateDir" }
    $state = @{
        schema_version = 1
        root = $TradeV2Root
        api = @{ pid = $apiProcess.Id; start_ticks = $apiProcess.StartTime.ToUniversalTime().Ticks }
        ui = @{ pid = $uiProcess.Id; start_ticks = $uiProcess.StartTime.ToUniversalTime().Ticks }
        api_url = 'http://127.0.0.1:8000/docs'
        ui_url = $TradeV2UiUrl
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $TradeV2StateFile -Encoding utf8
    Write-Host "Trade v2 ready: $TradeV2UiUrl"
    Write-Host 'API: http://127.0.0.1:8000/docs'
    Write-Host 'Stop: .\scripts\stop_trade_v2.ps1'
    if ($OpenBrowser) { Start-Process $TradeV2UiUrl }
} catch {
    foreach ($owned in @($apiProcess, $uiProcess)) {
        if ($null -ne $owned -and -not $owned.HasExited) {
            Stop-Process -Id $owned.Id -ErrorAction SilentlyContinue
        }
    }
    throw
}
