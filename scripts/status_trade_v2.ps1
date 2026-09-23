. (Join-Path $PSScriptRoot 'workstation_common.ps1')
$state = Get-TradeV2State
if ($null -eq $state) {
    @{ status = 'NOT_RUNNING'; api = 'OFF'; frontend = 'OFF'; ui_url = $TradeV2UiUrl } |
        ConvertTo-Json | Write-Output
    return
}
$api = Get-TradeV2OwnedProcess $state.api
$ui = Get-TradeV2OwnedProcess $state.ui
$apiHealthy = $null -ne $api -and (Get-TradeV2Health)
$uiHealthy = $null -ne $ui -and (Get-TradeV2UiHealth)
@{
    status = if ($apiHealthy -and $uiHealthy) { 'RUNNING' } else { 'DEGRADED' }
    api = if ($apiHealthy) { 'HEALTHY' } else { 'UNAVAILABLE' }
    frontend = if ($uiHealthy) { 'HEALTHY' } else { 'UNAVAILABLE' }
    api_pid = if ($null -ne $api) { $api.Id } else { $null }
    ui_pid = if ($null -ne $ui) { $ui.Id } else { $null }
    ui_url = $TradeV2UiUrl
    live = 'LIVE_DISABLED'
} | ConvertTo-Json | Write-Output
