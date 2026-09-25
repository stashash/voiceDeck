# Модели voiceDeck в LM Studio без срока простоя: Qwen3.8-27B на четыре запроса и эмбеддинги bge-m3.
# Запуск после перезагрузки машины: pwsh scripts/start-models.ps1
#
# Модель, загруженная по первому запросу, живёт 60 минут и грузится с настройками по умолчанию.
# При включённом Auto-Evict загрузка эмбеддингов выгружает Qwen, и наоборот: живой режим тогда
# ждёт модель. Модели, загруженные командой lms load без --ttl, остаются в памяти до выгрузки.
# Скрипт выгружает все модели LM Studio: voiceDeck занимает видеокарту целиком.

lms server start
lms unload --all
lms load qwen/qwen3.8-27b --gpu max -c 20480 --parallel 4 -y
if ($LASTEXITCODE -ne 0) { throw 'Qwen3.8-27B не загрузилась: скачайте её командой lms get qwen/qwen3.8-27b' }
lms load text-embedding-bge-m3 --identifier text-embedding-bge-m3 -y
if ($LASTEXITCODE -ne 0) { throw 'bge-m3 не загрузилась: скачайте её в LM Studio (text-embedding-bge-m3)' }
lms ps
