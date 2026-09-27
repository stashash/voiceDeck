param(
    [string]$SourceWorkspace = 'C:/Users/Admin/dev/project/voiceDeck',
    [switch]$Build
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$env:VOICEDECK_MODELS_DIR = Join-Path $SourceWorkspace 'models'
$env:VOICEDECK_NATIVE_DIR = Join-Path $SourceWorkspace 'native'
if (!(Test-Path -LiteralPath (Join-Path $env:VOICEDECK_MODELS_DIR 'config.json'))) {
    throw 'Existing local models/config.json is required. No downloads are performed.'
}
Push-Location $root
try {
    if ($Build) {
        docker build --pull=false --build-arg VITE_DESIGNER_URL=http://localhost:8191 -t voicedeck-app:voice-quality .
        if ($LASTEXITCODE -ne 0) { throw 'Voice-quality app build failed' }
    }
    docker compose -f compose.voice-quality.yaml up -d
    if ($LASTEXITCODE -ne 0) { throw 'Voice-quality stack failed to start; existing listeners were not stopped.' }
    Write-Output 'Voice-quality preview: http://localhost:8189/ . Isolated designer: http://localhost:8191/ .'
} finally { Pop-Location }
