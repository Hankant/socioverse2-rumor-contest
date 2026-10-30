param([string]$OutputRoot='')
$ErrorActionPreference='Stop'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $activePointer=Join-Path $PSScriptRoot 'runtime\v7\active_batch.json'
    if (Test-Path -LiteralPath $activePointer) {$OutputRoot=(Get-Content -LiteralPath $activePointer -Encoding UTF8 -Raw | ConvertFrom-Json).output}
    else {$OutputRoot='E:\papers\socioverse 2026\socioverse2_v6_local\Results_V7'}
}
$pointer=Get-Content -LiteralPath (Join-Path $outputRoot 'LATEST_BATCH.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$batchRoot=$pointer.batch_dir
$state=Get-Content -LiteralPath (Join-Path $batchRoot 'batch_status.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$controller=Get-Process -Id $state.pid -ErrorAction SilentlyContinue
Write-Host ('Batch status: '+$state.status)
Write-Host ('Controller PID: '+$state.pid+'; alive: '+[bool]$controller)
if (-not $controller) {Write-Host 'Controller has exited. The saved status and counts below are historical.' -ForegroundColor Yellow}
Write-Host ('Results: '+$outputRoot)
$state.cases.PSObject.Properties | ForEach-Object {
    [pscustomobject]@{Condition=$_.Name;Status=$_.Value.status;CompleteTicks=$_.Value.last_completed_tick;Error=$_.Value.error_type}
} | Format-Table -AutoSize
Get-Content -LiteralPath (Join-Path $batchRoot 'global-request-state.json') -Encoding UTF8 -ErrorAction SilentlyContinue
