param(
    [string]$Pdf = 'resource/mahler No.7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_in_E_minor_---_Full_Score_(Dover_Reprint).pdf',
    [string]$Pages = '1',
    [string]$Output = 'output/omr/mahler7',
    [int]$Dpi = 450,
    [int]$Retries = 1,
    [string]$Audiveris = '',
    [string]$MuseScore = $env:MUSESCORE_PATH,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$arguments = @('-m', 'backend.score_processing', $Pdf, '--pages', $Pages,
    '--output', $Output, '--dpi', "$Dpi", '--retries', "$Retries")
if ($Audiveris) { $arguments += @('--audiveris', $Audiveris) }
if ($MuseScore) { $arguments += @('--musescore', $MuseScore) }
if ($Force) { $arguments += '--force' }
Push-Location $projectRoot
try {
    & $python @arguments
    $conversionExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $conversionExitCode
