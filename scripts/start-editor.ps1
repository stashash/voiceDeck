param([switch]$Build)

$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $models = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
    foreach ($required in @('qwen3.8:27b', 'bge-m3-embed:latest')) {
        if ($required -notin $models.models.name) {
            throw "Ollama model missing: $required. No models were downloaded."
        }
    }
    $composeArgs = @('compose', '-f', 'compose.yaml', '-f', 'compose.editor.yaml', 'up', '-d')
    if ($Build) { $composeArgs += '--build' } else { $composeArgs += '--no-build' }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed.' }
    $deadline = (Get-Date).AddMinutes(3)
    do {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8088/health' -TimeoutSec 5
            $null = Invoke-RestMethod 'http://127.0.0.1:8090/design-systems' -TimeoutSec 5
            if ($health.status -eq 'ready' -and $health.mode -eq 'live') {
                Write-Host 'VoiceDeck ready: http://localhost:8088/'
                return
            }
        } catch {
            Write-Verbose $_
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Startup timed out. Inspect: docker compose -f compose.yaml -f compose.editor.yaml logs --tail 50'
} finally {
    Pop-Location
}
