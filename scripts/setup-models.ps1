$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskRoot = Split-Path $PSScriptRoot -Parent
$release = 'https://github.com/k2-fsa/sherpa-onnx/releases/download'
$hf = 'https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/2c4055b12046f11709e9df2c122e59ffbdc2f900'
$artifacts = @(
    @('native/sherpa-onnx-jvm-1.13.8.jar', "$release/v1.13.8/sherpa-onnx-jvm-1.13.8.jar", '77B7B047FADE4EADADA96B568EB92615049AAF1DC317C7244E46C1EA38B9A63B'),
    @('native/sherpa-onnx-native-lib-linux-x64-1.13.8.jar', "$release/v1.13.8/sherpa-onnx-native-lib-linux-x64-1.13.8.jar", '30C93B59381113F9C20AEDBBF9FC1AD399158F6BC03DDDC0F8934A6E28E069BA'),
    @('models/vad/silero_vad.onnx', "$release/asr-models/silero_vad.onnx", '9E2449E1087496D8D4CABA907F23E0BD3F78D91FA552479BB9C23AC09CBB1FD6'),
    @('models/gigaam.tar.bz2', "$release/asr-models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16.tar.bz2", '20E41E160EFA6F2460A7EF6554CDBBB9E8FFFB2B92E6BC708E9406BD8B9256EA'),
    @('models/semantic/model.onnx', "$hf/onnx/model_quantized.onnx", '66FC00F5F29AFCAFF34092E1BDD20008CA3918265A82FB9695A551E510CC4EBC'),
    @('models/semantic/tokenizer.json', "$hf/tokenizer.json", 'B60B6B43406A48BF3638526314F3D232D97058BC93472FF2DE930D43686FA441')
)
foreach ($artifact in $artifacts) {
    $destination = Join-Path $taskRoot $artifact[0]
    New-Item -ItemType Directory -Force (Split-Path $destination -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $destination)) {
        Write-Host "Downloading $($artifact[0])"
        Invoke-WebRequest $artifact[1] -OutFile "$destination.part"
        if ((Get-FileHash -LiteralPath "$destination.part").Hash -ne $artifact[2]) { throw "Checksum mismatch: $destination.part" }
        Move-Item -LiteralPath "$destination.part" -Destination $destination
    }
    if ((Get-FileHash -LiteralPath $destination).Hash -ne $artifact[2]) { throw "Checksum mismatch: $destination" }
}
$model = Join-Path $taskRoot 'models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16/model.int8.onnx'
if (-not (Test-Path -LiteralPath $model)) {
    tar -xjf (Join-Path $taskRoot 'models/gigaam.tar.bz2') -C (Join-Path $taskRoot 'models')
    if ($LASTEXITCODE -ne 0) { throw 'Model extraction failed' }
}
$config = Join-Path $taskRoot 'models/config.json'
if (-not (Test-Path -LiteralPath $config)) { Copy-Item -LiteralPath (Join-Path $taskRoot 'docs/live-models.json') -Destination $config }
$envFile = Join-Path $taskRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) { [System.IO.File]::WriteAllText($envFile, "MODE=live`nSLIDE_MODE=sketch`nAPP_PORT=8088`n") }
Write-Host 'Models verified. Set MODE=live and SLIDE_MODE=sketch in .env, then run docker compose up --build -d.'
