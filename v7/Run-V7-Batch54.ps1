param([string]$OutputRoot='')
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $activePointer=Join-Path $projectRoot 'runtime\v7\active_batch.json'
    if (Test-Path -LiteralPath $activePointer) {$OutputRoot=(Get-Content -LiteralPath $activePointer -Encoding UTF8 -Raw | ConvertFrom-Json).output}
    else {$OutputRoot='E:\papers\socioverse 2026\socioverse2_v6_local\Results_V7'}
}
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {$pythonPath=Join-Path (Split-Path -Parent $projectRoot) 'socioverse2_v6_local\.venv\Scripts\python.exe'}
if (-not (Test-Path -LiteralPath $pythonPath)) {throw 'Python dependencies are missing. Run Setup-V7.ps1.'}
$env:PYTHONIOENCODING='utf-8';$env:PYTHONUNBUFFERED='1'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
Push-Location -LiteralPath $projectRoot
try {
    $batchPointer=Get-Content -LiteralPath (Join-Path $OutputRoot 'LATEST_BATCH.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    $requestControls=Get-Content -LiteralPath (Join-Path $batchPointer.batch_dir 'request_controls.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    $host.UI.RawUI.WindowTitle="SocioVerse V7 - 54 conditions - shared API $($requestControls.max_global_concurrency)"
    $consoleLog=Join-Path $batchPointer.batch_dir 'console.log'
    # Windows PowerShell treats native stderr as ErrorRecord objects. Keep the
    # complete Python diagnostic instead of terminating on its first line.
    $savedErrorPreference=$ErrorActionPreference
    $ErrorActionPreference='Continue'
    try {
        & $pythonPath -u (Join-Path $projectRoot 'scripts\bootstrap_native_batch.py') --batch $batchPointer.batch_dir 2>&1 | Tee-Object -FilePath $consoleLog -Append
        $resultCode=$LASTEXITCODE
    } finally {$ErrorActionPreference=$savedErrorPreference}
} finally {Pop-Location}
Write-Host "V7 Batch controller exited: $resultCode. Inspect $OutputRoot\LATEST_BATCH.json."
Read-Host 'Press Enter to close'
exit $resultCode
