. (Join-Path $PSScriptRoot 'workstation_common.ps1')
try {
    $state = Get-TradeV2State
} catch {
    # Without readable state no process can be proven ours, so none is stopped.
    Remove-Item -LiteralPath $TradeV2StateFile -Force
    $listeners = @(8000, 5173 | ForEach-Object { Get-TradeV2Listeners -Port $_ })
    Write-Warning "Unreadable launcher state was removed; no process was stopped."
    if ($listeners.Count -gt 0) {
        Write-Warning "Ports 8000/5173 are still served by PID $($listeners -join ', '); stop them deliberately if they are Trade v2."
    }
    return
}
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
