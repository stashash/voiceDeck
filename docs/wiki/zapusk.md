# Запуск на своей машине

Порядок проверен 23 сентября 2026 года на Windows 11 с RTX 5090 Laptop (24 ГБ).

| Что нужно | Зачем |
|---|---|
| Windows 10 или 11, Docker Desktop с Linux-контейнерами | Java-сервис речи, сервис `designer`, PostgreSQL |
| [LM Studio](https://lmstudio.ai) | сервер модели на порту 1234 |
| Видеокарта NVIDIA от 24 ГБ | Qwen3.8-27B с контекстом 20k на четыре запроса занимает 22,7 ГБ |
| PowerShell 7 (`pwsh`), `tar`, Node.js 22 или новее | веса распознавания речи и сквозные прогоны |
| Python 3.12 | мост к CLI-агентам и тесты `designer` вне контейнера |
| Git | клонировать репозиторий |

Порядок написан для Windows и Docker Desktop. На Linux с Docker Engine он не проверялся. Там контейнеры ходят на хост не через `127.0.0.1`, поэтому LM Studio должен слушать внешний адрес: перед `scripts/start-models.ps1` задайте `LMS_SERVER_HOST=0.0.0.0` (параметр из `lms server start --help`). Сервер модели тогда виден и локальной сети. Скрипты `.ps1` требуют PowerShell 7.

## 1. Репозиторий и веса распознавания речи

1. Клонируйте репозиторий и перейдите в него:

   ```powershell
   git clone https://github.com/stashash/voiceDeck.git
   cd voiceDeck
   ```

2. Скачайте веса:

   ```powershell
   pwsh scripts/setup-models.ps1
   ```

Скрипт кладёт в `models/` GigaAM-v3, Silero VAD и MiniLM для смысловых фрагментов, в `native/` библиотеки sherpa-onnx и сверяет их SHA-256. Если `.env` ещё нет, он копирует `.env.example`: настройки там уже под LM Studio.

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

Менять ничего не нужно: `.env` из шага 1 уже содержит `MODE=live`, `SLIDE_MODE=designer` и адрес LM Studio. `MODE=live` включает микрофон, поле для текста вместо микрофона работает, пока не идёт запись. `SLIDE_MODE=designer` строит слайды Live-режима по дизайн-системе. Остальные переменные описаны в [README](../../README.md#переменные-окружения).

## 4. Стек

1. Соберите и поднимите контейнеры:

   ```powershell
   docker compose up --build -d
   ```

2. Проверьте Java-сервис: `curl http://127.0.0.1:8088/health` отвечает `"status":"ready"` и режимом из `.env`.
3. Проверьте `designer`: `curl http://127.0.0.1:8090/health` отвечает `"model_ok":true`.
4. Откройте в Chrome или Edge `http://localhost:8088`.

Первая сборка идёт несколько минут: в неё входят Java-тесты и LibreOffice для картинок слайдов. Контейнеры поднимаются сами после перезапуска Docker, модели в LM Studio нет: после перезагрузки машины запустите `scripts/start-models.ps1`.

## 5. CLI-агенты, по желанию

Qwen в LM Studio работает без этого шага. Чтобы слайды писали Claude Code, Codex, Cursor Agent или OpenCode, запустите в корне репозитория мост и оставьте окно открытым:

```powershell
python scripts/agent_bridge.py
```

Подробности и проверка агента: [агенты](agenty.md).

## 6. Первая дизайн-система

На свежей установке дизайн-систем нет. Откройте **Дизайн-системы**, нажмите кнопку загрузки и выберите любой pptx: [как это выглядит](prezentaciya-po-brifu.md#сделать-дизайн-систему-из-pptx).

Дальше: [презентация по брифу](prezentaciya-po-brifu.md) или [Live-режим](zhivoy-rezhim.md).
