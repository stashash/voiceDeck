param(
    [string]$SourceWorkspace = 'C:/Users/Admin/dev/project/voiceDeck',
    [switch]$Build
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$env:VOICEDECK_MODELS_DIR = Join-Path $SourceWorkspace 'models'
$env:VOICEDECK_NATIVE_DIR = Join-Path $SourceWorkspace 'native'
if (!(Test-Path -LiteralPath (Join-Path $env:VOICEDECK_MODELS_DIR 'config.json'))) {
    throw 'Existing local ASR models/config.json is required. No model downloads are performed.'
}
Push-Location $root
try {
    if ($Build) {
        docker build --pull=false --build-arg VITE_DESIGNER_URL=http://localhost:8091 -t voicedeck-app:voice-factory .
        if ($LASTEXITCODE -ne 0) { throw 'Factory app build failed' }
    }
    docker compose -f compose.voice-factory.yaml up -d
    if ($LASTEXITCODE -ne 0) { throw 'Factory stack failed to start' }
    $frontend = Join-Path $root 'frontend'
    if (!(Test-Path -LiteralPath (Join-Path $frontend 'node_modules/vite/bin/vite.js'))) {
        throw 'Run npm ci in frontend first.'
    }
    if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) {
        Write-Output 'Port 5174 is already in use. Existing process was not changed.'
        return
    }
    $logs = Join-Path $root '.voice-factory'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $env:APP_PROXY_URL = 'http://127.0.0.1:8089'
    $env:DESIGNER_PROXY_URL = 'http://127.0.0.1:8091'
    $env:VITE_DESIGNER_URL = 'http://localhost:8091'
    $process = Start-Process -FilePath (Get-Command node).Source -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5174','--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'vite.log') -RedirectStandardError (Join-Path $logs 'vite.err.log')
    Write-Output "Preview http://localhost:5174/ (Vite PID $($process.Id)); isolated API 8089, designer 8091."
} finally { Pop-Location }
