# Модели voiceDeck в LM Studio без срока простоя: Qwen3.8-27B на четыре запроса и эмбеддинги bge-m3.
# Запуск после перезагрузки машины: pwsh scripts/start-models.ps1
#
# Модель, загруженная по первому запросу, живёт 60 минут и грузится с настройками по умолчанию.
# При включённом Auto-Evict загрузка эмбеддингов выгружает Qwen, и наоборот: живой режим тогда
# ждёт модель. Модели, загруженные командой lms load без --ttl, остаются в памяти до выгрузки.
# Скрипт выгружает все модели LM Studio: voiceDeck занимает видеокарту целиком.

# Сразу после установки LM Studio lms ещё нет в PATH: он лежит в ~/.lmstudio/bin.
$lms = (Get-Command lms -ErrorAction SilentlyContinue).Source
if (-not $lms) { $lms = Join-Path $HOME '.lmstudio\bin\lms.exe' }
if (-not (Test-Path -LiteralPath $lms)) { throw 'Не найден lms: откройте LM Studio один раз, он кладёт lms в ~/.lmstudio/bin' }

& $lms server start
& $lms unload --all
& $lms load qwen/qwen3.8-27b --gpu max -c 20480 --parallel 4 -y
if ($LASTEXITCODE -ne 0) { throw 'Qwen3.8-27B не загрузилась: скачайте её командой lms get qwen/qwen3.8-27b' }
& $lms load text-embedding-bge-m3 --identifier text-embedding-bge-m3 -y
if ($LASTEXITCODE -ne 0) { throw 'bge-m3 не загрузилась: скачайте её командой lms get https://huggingface.co/lm-kit/bge-m3-gguf/blob/main/bge-m3-Q8_0.gguf' }
& $lms ps
