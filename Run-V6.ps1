param(
    [ValidateSet('Preview','Offline','Live','Design','Doctor','Status','Tests','Resume','Verify')]
    [string]$Mode = 'Preview',
    [ValidateSet(0,0.2,0.4)][double]$TrustGap = 0.4,
    [ValidateSet(2,4,7)][int]$GovernmentTick = 2,
    [ValidateSet(0.2,0.8)][double]$Targeting = 0.8,
    [ValidateSet(0.25,0.5,0.75)][double]$GovernmentTrust = 0.75,
    [ValidateRange(1,10)][int]$Concurrency = 10,
    [ValidateRange(1,40)][int]$Steps = 10,
    [ValidateRange(1,12200)][int]$MaxRequests = 12200,
    [string]$ParentRun,
    [string]$RunDir,
    [int]$PromptLimit = 0,
    [long]$InputBudget = 0,
    [long]$OutputBudget = 0,
    [switch]$NoInteractiveRecovery
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Missing .venv. Run Setup-V6.ps1 first.' }
$env:PYTHONIOENCODING = 'utf-8'
Push-Location -LiteralPath $projectRoot
try {
    if ($Mode -eq 'Tests') {
        & $pythonPath -m pytest app_v6 -q -p no:cacheprovider
    } else {
        $cliArgs = @('app_v6/local_cli.py', $Mode.ToLowerInvariant())
        if ($Mode -in @('Preview','Offline','Live','Design')) {
            $culture = [System.Globalization.CultureInfo]::InvariantCulture
            $cliArgs += @('--gap',$TrustGap.ToString($culture),'--tg',"$GovernmentTick",
                '--target',$Targeting.ToString($culture),'--gt',$GovernmentTrust.ToString($culture),
                '--concurrency',"$Concurrency",'--steps',"$Steps",'--max-requests',"$MaxRequests")
        }
        if ($Mode -eq 'Resume') {
            if ($ParentRun) { $cliArgs += @('--parent',$ParentRun) }
        }
        if ($Mode -eq 'Verify') {
            if (-not $RunDir) { throw 'Verify needs -RunDir.' }
            $cliArgs += @('--run-dir',$RunDir)
        }
        if ($Mode -in @('Preview','Offline','Live','Design','Resume')) {
            if ($PromptLimit -gt 0) { $cliArgs += @('--prompt-limit',"$PromptLimit") }
            if ($InputBudget -gt 0) { $cliArgs += @('--input-budget',"$InputBudget") }
            if ($OutputBudget -gt 0) { $cliArgs += @('--output-budget',"$OutputBudget") }
            if ($NoInteractiveRecovery) { $cliArgs += '--no-interactive-recovery' }
        }
        & $pythonPath @cliArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "V6 process ended with exit code $LASTEXITCODE. See its diagnostic above." }
} finally {
    Pop-Location
}
