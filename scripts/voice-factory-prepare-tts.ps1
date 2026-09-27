param([switch]$DownloadEspeak)
$ErrorActionPreference = 'Stop'
$output = Join-Path $PSScriptRoot 'voice-factory-output'
$voices = New-Object -ComObject SAPI.SpVoice
$inventory = @($voices.GetVoices() | ForEach-Object {
    [pscustomobject]@{name=$_.GetDescription(); id=$_.Id; language=$_.GetAttribute('Language')}
})
$registryVoices = @()
foreach ($registryRoot in @('HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens','HKCU:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens')) {
    $registryVoices += @(Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue | ForEach-Object {
        $attributes = Get-ItemProperty -LiteralPath ($_.PSPath + '\Attributes') -ErrorAction SilentlyContinue
        [pscustomobject]@{id=$_.Name;name=$attributes.Name;language=$attributes.Language}
    })
}
$availability = [pscustomobject]@{sapi=$inventory;oneCoreAnd32Bit=$registryVoices}
$availability | ConvertTo-Json -Depth 4
if (-not $DownloadEspeak) { return }

# Administrative extraction creates a portable tree; it does not install voices.
New-Item -ItemType Directory -Path $output -Force | Out-Null
$installer = Join-Path $output 'espeak-ng-1.52.0.msi'
$portable = Join-Path $output 'espeak-ng-1.52.0'
$url = 'https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi'
if (-not (Test-Path -LiteralPath $installer)) { Invoke-WebRequest -Uri $url -OutFile $installer }
if ((Get-Item -LiteralPath $installer).Length -ne 12765862) { throw 'Unexpected eSpeak release size' }
$digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($digest -ne '7F673C709EA5DD579D3B5EBB98688CC575328A6AB7438D2BC405B88CEDAEAFB9') { throw 'Unexpected eSpeak release hash' }
$process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/a', ('"'+$installer+'"'), '/qn', ('TARGETDIR="'+$portable+'"')) -WindowStyle Hidden -PassThru -Wait
if ($process.ExitCode -ne 0) { throw "Portable extraction failed: $($process.ExitCode)" }
$exe = Get-ChildItem -LiteralPath $portable -Filter 'espeak-ng.exe' -Recurse | Select-Object -First 1
if (-not $exe) { throw 'Portable eSpeak executable not found' }
[pscustomobject]@{source=$url;sha256=$digest;executable=$exe.FullName;voices=$availability} |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'tts-provenance.json') -Encoding UTF8
$previousDataPath = $env:ESPEAK_DATA_PATH
try {
    $env:ESPEAK_DATA_PATH = $exe.DirectoryName
    & $exe.FullName '--voices=ru'
    if ($LASTEXITCODE -ne 0) { throw "eSpeak voice probe failed: $LASTEXITCODE" }
} finally { $env:ESPEAK_DATA_PATH = $previousDataPath }
Write-Output $exe.FullName
