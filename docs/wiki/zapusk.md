# Запуск на своей машине

Порядок проверен 23 сентября 2026 года на Windows 11 с RTX 5090 Laptop (24 ГБ).

| Что нужно | Зачем |
|---|---|
| Windows 10 или 11, Docker Desktop с Linux-контейнерами | Java-сервис речи, сервис `designer`, PostgreSQL |
| [LM Studio](https://lmstudio.ai) | сервер модели на порту 1234 |
| Видеокарта NVIDIA от 24 ГБ | Qwen3.8-27B с контекстом 20k на четыре запроса занимает 22,7 ГБ |
| PowerShell, `tar`, Node.js 22 или новее | веса распознавания речи и сквозные прогоны |
| Python 3.12 | только для тестов `designer` вне контейнера |

## 1. Веса распознавания речи

1. В корне репозитория выполните:

   ```powershell
   ./scripts/setup-models.ps1
   ```

Скрипт кладёт в `models/` GigaAM-v3, Silero VAD и библиотеки sherpa-onnx и сверяет их SHA-256.

## 2. Модели в LM Studio

1. Скачайте модель:

   ```powershell
   lms get qwen/qwen3.8-27b
   ```

2. Скачайте в LM Studio эмбеддинги bge-m3: в списке моделей она значится как `text-embedding-bge-m3`.
3. Загрузите обе модели без срока простоя:

   ```powershell
   pwsh scripts/start-models.ps1
   ```

4. Проверьте вывод: `qwen/qwen3.8-27b` с `PARALLEL 4` и `text-embedding-bge-m3`, колонка `TTL` пустая.

Модель, которую LM Studio грузит сама по первому запросу, живёт 60 минут, и загрузка эмбеддингов выгружает Qwen. Скрипт закрепляет обе модели, пока их не выгрузят вручную. Он же нужен после каждой перезагрузки машины.

## 3. Настройки

1. Скопируйте пример:

   ```powershell
   Copy-Item .env.example .env
   ```

2. В `.env` замените эти строки:

   ```ini
   MODE=live
   SLIDE_MODE=designer
   EMBEDDING_URL=http://host.docker.internal:1234/v1
   EMBEDDING_MODEL=text-embedding-bge-m3
   ```

`MODE=live` включает микрофон, `MODE=demo` вместо него даёт поле для текста. `SLIDE_MODE=designer` строит живые слайды по шаблону. Остальные переменные описаны в [README](../../README.md#переменные-окружения).

## 4. Стек

1. Соберите и поднимите контейнеры:

   ```powershell
   docker compose up --build -d
   ```

2. Проверьте Java-сервис: `curl http://127.0.0.1:8088/health` отвечает `"status":"ready"` и режимом из `.env`.
3. Проверьте `designer`: `curl http://127.0.0.1:8090/health` отвечает `"model_ok":true`.
4. Откройте в Chrome или Edge `http://localhost:8088`.

Первая сборка идёт несколько минут: в неё входят Java-тесты и LibreOffice для картинок слайдов. Контейнеры поднимаются сами после перезапуска Docker, модели в LM Studio нет: после перезагрузки машины запустите `scripts/start-models.ps1`.

Дальше: [презентация по брифу](prezentaciya-po-brifu.md) или [живой режим](zhivoy-rezhim.md).
