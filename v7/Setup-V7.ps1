$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.12 -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) {throw 'Could not create the Python 3.12 environment.'}
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m pip install -r .\requirements.txt -c .\constraints.txt
    if ($LASTEXITCODE -ne 0) {throw 'Dependency installation failed.'}
    & $pythonPath (Join-Path $projectRoot 'app_v7\local_cli.py') doctor
    $resultCode=$LASTEXITCODE
} finally {Pop-Location}
exit $resultCode
