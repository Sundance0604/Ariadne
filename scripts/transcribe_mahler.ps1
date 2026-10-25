param(
    [ValidateRange(1, 5)][int]$Movement = 1,
    [int]$ThroughPage = 0,
    [int]$BatchSize = 4,
    [int]$Dpi = 450,
    [switch]$Status
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$arguments = @('-m', 'backend.score_processing.movements', '--movement', "$Movement",
    '--batch-size', "$BatchSize", '--dpi', "$Dpi")
if ($ThroughPage -gt 0) { $arguments += @('--through-page', "$ThroughPage") }
if ($Status) { $arguments += '--status' }
Push-Location $projectRoot
try {
    & $python @arguments
    $conversionExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $conversionExitCode
