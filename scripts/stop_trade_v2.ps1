. (Join-Path $PSScriptRoot 'workstation_common.ps1')
$state = Get-TradeV2State
if ($null -eq $state) {
    Write-Host 'Trade v2 launcher is already stopped.'
    return
}
if ($state.root -ne $TradeV2Root) {
    throw 'Launcher state belongs to a different repository; refusing to stop processes.'
}
foreach ($record in @($state.api, $state.ui)) {
    $owned = Get-TradeV2OwnedProcess $record
    if ($null -ne $owned) {
        Stop-Process -Id $owned.Id -ErrorAction Stop
        Write-Host "Stopped owned PID $($owned.Id)"
    }
}
Remove-Item -LiteralPath $TradeV2StateFile -Force
Write-Host 'Trade v2 launcher stopped. No unrelated process was touched.'
