param(
    [ValidateSet('text','audio','stop')][string]$Mode = 'text',
    [string]$RunLabel = '',
    [string]$Manifest = '',
    [string]$PriorFixture = 'C:/Users/Admin/dev/project/voiceDeck/.codex-build/editor-verification/text-command.wav'
)
$ErrorActionPreference = 'Stop'
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) { $node = 'C:/Program Files/nodejs/node.exe' }
if (-not (Test-Path -LiteralPath $node)) { throw 'Node 22+ is required' }
if (-not $RunLabel) { $RunLabel = 'acceptance-' + $Mode + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') }
if ($RunLabel -notmatch '^[a-z0-9-]+$') { throw 'Invalid run label' }
if (-not $Manifest) { $Manifest = Join-Path $PSScriptRoot 'voice-factory-output/audio/manifest.json' }
$variables = @('VOICE_FACTORY_LIVE','VITE_DESIGNER_URL','VOICE_FACTORY_AUDIO_URL','VOICE_FACTORY_AUDIO_MANIFEST','VOICE_FACTORY_PRIOR_FIXTURE','VOICE_FACTORY_RUN_LABEL','VOICE_FACTORY_TRAILING_SILENCE_MS')
$previous = @{}
foreach ($name in $variables) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:VOICE_FACTORY_LIVE = '1'
    $env:VITE_DESIGNER_URL = 'http://127.0.0.1:8091'
    $env:VOICE_FACTORY_AUDIO_URL = 'http://127.0.0.1:8089'
    $env:VOICE_FACTORY_RUN_LABEL = $RunLabel
    $env:VOICE_FACTORY_TRAILING_SILENCE_MS = if ($Mode -eq 'stop') { '0' } else { '1000' }
    $env:VOICE_FACTORY_AUDIO_MANIFEST = $null
    $env:VOICE_FACTORY_PRIOR_FIXTURE = $null
    if ($Mode -ne 'text') {
        $env:VOICE_FACTORY_AUDIO_MANIFEST = (Resolve-Path -LiteralPath $Manifest).Path
        if (Test-Path -LiteralPath $PriorFixture) { $env:VOICE_FACTORY_PRIOR_FIXTURE = (Resolve-Path -LiteralPath $PriorFixture).Path }
    }
    & $node --test (Join-Path $PSScriptRoot 'voice-factory-audio.test.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'Audio transport guard tests failed' }
    Push-Location (Join-Path (Split-Path $PSScriptRoot -Parent) 'frontend')
    try {
        & $node node_modules/vitest/vitest.mjs run src/stage/voiceFactoryHoldout.test.ts src/stage/voiceFactoryAcceptance.test.ts
        $result = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
if ($result -ne 0) { throw "Acceptance failed (exit $result). See scripts/voice-factory-output/$RunLabel.json" }
