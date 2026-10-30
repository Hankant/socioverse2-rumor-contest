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
$env:PYTHONIOENCODING='utf-8'
& $pythonPath (Join-Path $projectRoot 'app_v7\batch54.py') --pause --output $OutputRoot
exit $LASTEXITCODE
