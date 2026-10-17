# Сервер картинок voiceDeck: ComfyUI на порту 8189 с FLUX.2 klein 4B (Apache 2.0).
# Запуск: pwsh scripts/start-images.ps1 [-ComfyDir <каталог ComfyUI>] [-ModelPaths <extra_model_paths.yaml>]
#
# designer ходит сюда по DESIGNER_IMAGE_URL (из контейнера http://host.docker.internal:8189). Нужные файлы весов
# (README, раздел «Картинки в слайдах»): diffusion_models/flux-2-klein-4b-fp8.safetensors,
# text_encoders/qwen_3_4b.safetensors, vae/flux2-vae.safetensors.
#
# Видеокарта одна на всех: с инференсом VK текстовая модель работает удалённо, и ComfyUI (около 9 ГБ видеопамяти)
# помещается рядом с эмбеддингами bge-m3. С локальной Qwen3.8-27B в LM Studio на 24 ГБ вместе они не помещаются.
param(
    [string]$ComfyDir = (Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Installs\ComfyUI'),
    [string]$ModelPaths = '',
    [int]$Port = 8189
)

$python = Join-Path $ComfyDir 'standalone-env\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
$main = Join-Path $ComfyDir 'ComfyUI\main.py'
if (-not (Test-Path -LiteralPath $main)) { $main = Join-Path $ComfyDir 'main.py' }
if (-not (Test-Path -LiteralPath $main)) { throw "Не найден ComfyUI в $ComfyDir: укажите -ComfyDir" }

$free = (nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | Select-Object -First 1)
if ([int]$free -lt 10000) { Write-Warning "Свободно видеопамяти $free МБ: картинкам нужно около 9 ГБ, выгрузите локальную модель" }

$arguments = @($main, '--port', $Port, '--listen', '127.0.0.1', '--disable-auto-launch')
if ($ModelPaths) { $arguments += @('--extra-model-paths-config', $ModelPaths) }
Write-Host "ComfyUI: http://127.0.0.1:$Port, остановка Ctrl+C"
& $python @arguments
