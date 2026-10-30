param(
    [ValidateSet('live','preview','resume','status','doctor','verify')][string]$Mode='live',
    [string]$Config='',
    [int]$Steps=10,
    [string]$RunDir=''
)
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath=Join-Path (Split-Path -Parent $projectRoot) 'socioverse2_v6_local\.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python dependencies missing. Run Setup-V7.ps1 first.' }
$env:PYTHONIOENCODING='utf-8'
$launchArgs=@((Join-Path $projectRoot 'app_v7\local_cli.py'),$Mode,'--steps',"$Steps")
if ($Config) {$launchArgs+=@('--config',$Config)}
if ($RunDir) {$launchArgs+=@('--run-dir',$RunDir)}
Push-Location -LiteralPath $projectRoot
try { & $pythonPath @launchArgs; $resultCode=$LASTEXITCODE }
finally {Pop-Location}
exit $resultCode
