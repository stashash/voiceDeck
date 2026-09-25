# Запуск на своей машине

## Мастер установки

1. Клонируйте репозиторий:

   ```bash
   git clone https://github.com/stashash/voiceDeck.git
   cd voiceDeck
   ```

2. Запустите мастер: `setup.cmd` на Windows, `./setup.sh` на macOS.
3. Выберите, откуда брать модель: LM Studio или Ollama на этой машине, внешний OpenAI-совместимый API или без модели.
4. На вопросы «Поставить Docker Desktop?», «Поставить LM Studio?» или «Поставить Ollama?» ответьте «д», если программы ещё нет. Мастер ставит её через winget на Windows и через Homebrew на macOS.
5. Дождитесь строки `voiceDeck работает: http://localhost:8088`: браузер откроется сам.

В приложении сразу есть три дизайн-системы из шаблонов VK и три готовые презентации, у каждой три варианта вёрстки. Мастер можно запускать повторно: скачанное он не качает заново, в `.env` меняет только строки про модель. Без вопросов, например для проверки: `setup.cmd -Model none -Yes` или `VD_MODEL=none VD_YES=1 ./setup.sh`; вместо `none` подходят `lmstudio`, `ollama` и `api`.

Если Docker Desktop ставится впервые, Windows может попросить перезагрузку, а сам Docker Desktop попросит принять соглашение в своём окне. После этого запустите мастер снова.

## Вручную

Порядок проверен 23 сентября 2026 года на Windows 11 с RTX 5090 Laptop (24 ГБ).

| Что нужно | Зачем |
|---|---|
| Windows 10 или 11, Docker Desktop с Linux-контейнерами | Java-сервис речи, сервис `designer`, PostgreSQL |
| [LM Studio](https://lmstudio.ai) | сервер модели на порту 1234 |
| Видеокарта NVIDIA от 24 ГБ | Qwen3.8-27B с контекстом 20k на четыре запроса занимает 22,7 ГБ |
| PowerShell, `tar`, Node.js 22 или новее | веса распознавания речи и сквозные прогоны |
| Python 3.12 | мост к CLI-агентам и тесты `designer` вне контейнера |
| Git | клонировать репозиторий |

Порядок написан для Windows и Docker Desktop. На Linux с Docker Engine он не проверялся. Там контейнеры ходят на хост не через `127.0.0.1`, поэтому LM Studio должен слушать внешний адрес: перед `scripts/start-models.ps1` задайте `LMS_SERVER_HOST=0.0.0.0` (параметр из `lms server start --help`). Сервер модели тогда виден и локальной сети.

### 1. Репозиторий и веса распознавания речи

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

### 2. Модели в LM Studio

1. Скачайте модель и эмбеддинги bge-m3:

   ```powershell
   lms get qwen/qwen3.8-27b -y
   lms get https://huggingface.co/lm-kit/bge-m3-gguf/blob/main/bge-m3-Q8_0.gguf -y
   ```

2. Загрузите обе модели без срока простоя:

   ```powershell
   pwsh scripts/start-models.ps1
   ```

3. Проверьте вывод: `qwen/qwen3.8-27b` с `PARALLEL 4` и `text-embedding-bge-m3`, колонка `TTL` пустая.

Модель, которую LM Studio грузит сама по первому запросу, живёт 60 минут, и загрузка эмбеддингов выгружает Qwen. Скрипт закрепляет обе модели, пока их не выгрузят вручную. Он же нужен после каждой перезагрузки машины.

### Ollama вместо LM Studio

Путь написан по документации Ollama и на живой Ollama не запускался. У Ollama контекст 4096 токенов по умолчанию, промпты `designer` длиннее, поэтому модель создаётся заново с контекстом 20480:

```powershell
ollama pull qwen3.8:27b
ollama pull bge-m3
"FROM qwen3.8:27b`nPARAMETER num_ctx 20480" | Set-Content -Encoding ascii voicedeck.Modelfile
ollama create voicedeck-qwen3.8 -f voicedeck.Modelfile
```

В `.env` замените адреса и имена моделей:

```
DESIGNER_LLM_URL=http://host.docker.internal:11434/v1
DESIGNER_LLM_MODEL=voicedeck-qwen3.8
DESIGNER_LLM_PARALLEL=1
EMBEDDING_URL=http://host.docker.internal:11434/v1
EMBEDDING_MODEL=bge-m3
```

Ollama по умолчанию отвечает на один запрос за раз, поэтому `DESIGNER_LLM_PARALLEL=1`. На Linux Ollama должна слушать `0.0.0.0`: `OLLAMA_HOST=0.0.0.0:11434` через `sudo systemctl edit ollama`.

### 3. Настройки

Менять ничего не нужно: `.env` из шага 1 уже содержит `MODE=live`, `SLIDE_MODE=designer` и адрес LM Studio. Без `.env` `docker compose` берёт те же значения: они записаны умолчаниями в `compose.yaml`. Если весов распознавания речи нет, Java-сервис стартует без микрофона и пишет в журнал, что скачать. `MODE=live` включает микрофон, поле для текста вместо микрофона работает, пока не идёт запись. `SLIDE_MODE=designer` строит слайды Live-режима по дизайн-системе. Остальные переменные описаны в [README](../../README.md#переменные-окружения).

### 4. Стек

1. Соберите и поднимите контейнеры:

   ```powershell
   docker compose up --build -d
   ```

2. Проверьте Java-сервис: `curl http://127.0.0.1:8088/health` отвечает `"status":"ready"` и режимом из `.env`.
3. Проверьте `designer`: `curl http://127.0.0.1:8090/health` отвечает `"model_ok":true`.
4. Откройте в Chrome или Edge `http://localhost:8088`.

Первая сборка идёт несколько минут: в неё входят Java-тесты и LibreOffice для картинок слайдов. Контейнеры поднимаются сами после перезапуска Docker, модели в LM Studio нет: после перезагрузки машины запустите `scripts/start-models.ps1`.

### 5. CLI-агенты, по желанию

Qwen в LM Studio работает без этого шага. Чтобы слайды писали Claude Code, Codex, Cursor Agent или OpenCode, запустите в корне репозитория мост и оставьте окно открытым:

```powershell
python scripts/agent_bridge.py
```

Подробности и проверка агента: [агенты](agenty.md).

### 6. Готовые данные и своя дизайн-система

При первом старте сервис переносит из `demo/` три дизайн-системы из шаблонов VK и три презентации по три варианта вёрстки. Свою систему добавьте в разделе **Дизайн-системы**: кнопка загрузки, любой pptx, [как это выглядит](prezentaciya-po-brifu.md#сделать-дизайн-систему-из-pptx).

Дальше: [презентация по брифу](prezentaciya-po-brifu.md) или [Live-режим](zhivoy-rezhim.md).
