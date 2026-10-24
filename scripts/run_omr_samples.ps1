$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$audiveris = Join-Path $projectRoot '.tools/audiveris-portable/Audiveris/Audiveris.exe'
if (-not (Test-Path -LiteralPath $audiveris)) { throw 'Prepare the official Audiveris portable files first; see reports/omr-review.md.' }
$renderRoot = Join-Path $projectRoot 'tmp/omr'
New-Item -ItemType Directory -Force -Path $renderRoot | Out-Null
$assets = Join-Path $projectRoot 'resource/ravel left hand piano concerto'
$samples = @(
    @{ name = 'modern-opening'; pdf = 'maurice-ravel-piano-concerto-for-the-left-hand.pdf'; page = 1 },
    @{ name = 'modern-ending'; pdf = 'maurice-ravel-piano-concerto-for-the-left-hand.pdf'; page = 100 },
    @{ name = 'scan-opening'; pdf = 'IMSLP01581-Ravel_-_Piano_Concerto_for_the_Left_Hand_(Orchestral_Score).pdf'; page = 3 },
    @{ name = 'scan-ending'; pdf = 'IMSLP01581-Ravel_-_Piano_Concerto_for_the_Left_Hand_(Orchestral_Score).pdf'; page = 99 }
)
$samplePaths = @()
foreach ($sample in $samples) {
    $prefix = Join-Path $renderRoot $sample.name
    & pdftoppm -r 300 -f $sample.page -l $sample.page -png -singlefile (Join-Path $assets $sample.pdf) $prefix
    if ($LASTEXITCODE -ne 0) { throw "PDF render failed: $($sample.name)" }
    $samplePaths += ($prefix + '.png')
}
$previousAppData = $env:APPDATA
$previousLocalData = $env:LOCALAPPDATA
$previousJavaOptions = $env:JAVA_TOOL_OPTIONS
try {
    $env:APPDATA = Join-Path $projectRoot '.tools/audiveris-data'
    $env:LOCALAPPDATA = Join-Path $projectRoot '.tools/audiveris-data/local'
    $env:JAVA_TOOL_OPTIONS = '-Djava.io.tmpdir=' + (Join-Path $projectRoot 'tmp/java') + ' -Dorg.bytedeco.javacpp.cachedir=' + (Join-Path $projectRoot '.tools/javacpp')
    & $audiveris -batch -transcribe -export -save -output (Join-Path $projectRoot 'output/omr/samples') -- @samplePaths
    if ($LASTEXITCODE -ne 0) { throw 'Audiveris exited with an error; inspect the per-book logs.' }
} finally {
    $env:APPDATA = $previousAppData
    $env:LOCALAPPDATA = $previousLocalData
    $env:JAVA_TOOL_OPTIONS = $previousJavaOptions
}
