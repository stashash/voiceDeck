param(
    [string]$Label = 'asr-ranges-baseline',
    [string]$PriorFixture = 'C:/Users/Admin/dev/project/voiceDeck/.codex-build/editor-verification/text-command.wav'
)
$ErrorActionPreference = 'Stop'
if ($Label -notmatch '^[a-z0-9-]+$') { throw 'Invalid report label' }
$docker = 'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
$container = 'voicedeck-voice-factory-app-1'
$project = & $docker inspect $container --format '{{index .Config.Labels "com.docker.compose.project"}}'
if ($project -ne 'voicedeck-voice-factory') { throw 'Isolated app container required' }
$image = & $docker inspect $container --format '{{.Image}}'
$output = Join-Path $PSScriptRoot 'voice-factory-output'
New-Item -ItemType Directory -Path (Join-Path $output 'classes') -Force | Out-Null
& $docker cp "${container}:/app/app.jar" (Join-Path $output 'diagnostic-app.jar')
if ($LASTEXITCODE -ne 0) { throw 'Cannot read isolated app artifact' }
& $docker run --rm --network none --pull=never --entrypoint javac -v "${PSScriptRoot}:/verification" maven:3.9.9-eclipse-temurin-21 -cp /verification/voice-factory-output/diagnostic-app.jar -d /verification/voice-factory-output/classes /verification/voice-factory-asr-diagnostic.java
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic compilation failed' }
$inputs = @('select','size','color','move','replace','append','undo','next','previous') | ForEach-Object { "/verification/voice-factory-output/audio/$_.wav" }
if (Test-Path -LiteralPath $PriorFixture) {
    Copy-Item -LiteralPath $PriorFixture -Destination (Join-Path $output 'prior-text-command.wav')
    $inputs += '/verification/voice-factory-output/prior-text-command.wav'
}
& $docker run --rm --network none --pull=never --volumes-from "${container}:ro" -e MODEL_CONFIG=/models/config.json -e EMBEDDING_BACKEND=ollama --entrypoint java -v "${PSScriptRoot}:/verification" $image -cp '/app/app.jar:/native/*:/verification/voice-factory-output/classes' VoiceFactoryAsrDiagnostic "/verification/voice-factory-output/$Label.json" @inputs
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic failed' }
[pscustomobject]@{image=$image;container=$container;network='none';sourceFixture=$PriorFixture;completedAt=(Get-Date).ToUniversalTime().ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output "$Label-runtime.json") -Encoding UTF8
Write-Output "Image: $image"
Write-Output (Join-Path $output "$Label.json")
