# VoiceDeck

Локальный сервис презентаций: дизайн-система из любого pptx, презентация по брифу и слайды вслед за речью спикера.

Две части. Сервис `designer` читает незнакомый pptx-шаблон как дизайн-систему и собирает по брифу презентацию в его стиле: три варианта вёрстки, аудит, pptx из родных объектов, HTML и PDF (ТЗ VK Tech). Java-сервис слушает русскую речь, режет её на смысловые фрагменты и через тот же `designer` рисует слайды в стиле шаблона вслед за словами спикера.

Запуск на своей машине, проверка обоих режимов и тесты по шагам: [вики](docs/wiki/README.md).

## Быстрый старт

```bash
git clone https://github.com/stashash/voiceDeck.git
cd voiceDeck
```

Затем мастер установки: `setup.cmd` на Windows, `./setup.sh` на macOS.

Мастер спрашивает, откуда брать модель, и ставит недостающее, спросив согласия: Docker Desktop, LM Studio, Qwen3.8 27B, веса распознавания речи. Он пишет `.env`, собирает и поднимает контейнеры, проверяет сервисы и открывает `http://localhost:8088`. Повторный запуск пропускает сделанное.

| Модель | Что нужно | Что работает |
|---|---|---|
| LM Studio на этой машине | видеокарта NVIDIA от 24 ГБ или Mac на Apple Silicon от 32 ГБ, около 30 ГБ на диске | всё: генерация, правка, Live-режим |
| внешний OpenAI-совместимый API с Qwen3.8 27B | адрес, имя модели и ключ | всё; в Live границы мыслей идут по паузам речи |
| без модели | только Docker | готовые дизайн-системы и презентации, правка текста и образца, скачивание |

Сразу после установки в приложении есть три дизайн-системы из шаблонов VK и три презентации по одному брифу из `examples/brief.txt`, у каждой три варианта вёрстки: всего 9 вариантов, как требует ТЗ. Их копия лежит в `demo/`, при первом старте сервис переносит её в своё хранилище.

Ручная установка по шагам с проверкой каждого: [запуск на своей машине](docs/wiki/zapusk.md). Мастер для Windows проверен на Windows 11 всеми тремя путями модели. Для macOS проверены шаги до запуска контейнеров в bash 3.2 под arm64 и сборка обоих образов под arm64; на живом Mac мастер не запускался.

## Готовые презентации

Один бриф, три шаблона VK, три варианта вёрстки: `a` как в шаблоне, `b` плотнее, `c` данные вперёд. Шаблоны лежат в `docs/requirements/template/`, пересобрать всё заново: `python examples/build.py examples/brief.txt` и `python examples/export_demo.py <каталог данных designer>`.

| Шаблон | Вариант a | Вариант b | Вариант c |
|---|---|---|---|
| VK Tech шаблон | [pdf](demo/decks/vk-tech-shablon/a/files/deck.pdf), [pptx](demo/decks/vk-tech-shablon/a/files/deck.pptx), [html](demo/decks/vk-tech-shablon/a/files/deck.html) | [pdf](demo/decks/vk-tech-shablon/b/files/deck.pdf), [pptx](demo/decks/vk-tech-shablon/b/files/deck.pptx), [html](demo/decks/vk-tech-shablon/b/files/deck.html) | [pdf](demo/decks/vk-tech-shablon/c/files/deck.pdf), [pptx](demo/decks/vk-tech-shablon/c/files/deck.pptx), [html](demo/decks/vk-tech-shablon/c/files/deck.html) |
| VK WorkSpace Клиентская конференция Шаблон 03 | [pdf](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/a/files/deck.pdf), [pptx](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/a/files/deck.pptx), [html](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/a/files/deck.html) | [pdf](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/b/files/deck.pdf), [pptx](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/b/files/deck.pptx), [html](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/b/files/deck.html) | [pdf](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/c/files/deck.pdf), [pptx](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/c/files/deck.pptx), [html](demo/decks/vk-workspace-klientskaya-konferenciya-shablon-03/c/files/deck.html) |
| Шаблон презентации VK Education | [pdf](demo/decks/shablon-prezentacii-vk-education/a/files/deck.pdf), [pptx](demo/decks/shablon-prezentacii-vk-education/a/files/deck.pptx), [html](demo/decks/shablon-prezentacii-vk-education/a/files/deck.html) | [pdf](demo/decks/shablon-prezentacii-vk-education/b/files/deck.pdf), [pptx](demo/decks/shablon-prezentacii-vk-education/b/files/deck.pptx), [html](demo/decks/shablon-prezentacii-vk-education/b/files/deck.html) | [pdf](demo/decks/shablon-prezentacii-vk-education/c/files/deck.pdf), [pptx](demo/decks/shablon-prezentacii-vk-education/c/files/deck.pptx), [html](demo/decks/shablon-prezentacii-vk-education/c/files/deck.html) |

## Сервис `designer`: генерация презентаций по шаблону

Отдельный Python-сервис в `designer/`. Решает три бизнес-задачи ТЗ VK Tech:

1. Разбирает загруженный pptx-шаблон на дизайн-систему: токены (цвета, шрифты, шкала кеглей, поля), ассеты и слайды-образцы как паттерны вёрстки.
2. По брифу, назначению, аудитории и числу слайдов строит план колоды: состав, порядок и текст слайдов, до вёрстки.
3. По плану и шаблону собирает слайды: подбирает паттерн, заполняет слоты, вставляет диаграмму или таблицу, экспортирует pptx нативными объектами, html и pdf, прогоняет аудит.

Устройство конвейера — [ARCHITECTURE.md](ARCHITECTURE.md), модели — [MODELS.md](MODELS.md), проверки аудита — [AUDIT.md](AUDIT.md).

### Запуск

Сервис входит в `compose.yaml` третьим контейнером (`designer`, порт 8090, образ с LibreOffice и poppler для картинок слайдов): `docker compose up --build -d` поднимает базу, Java-сервис и `designer` разом. Без docker сервис запускается локально из каталога `designer`; на Windows картинки слайдов тогда снимает PowerPoint через постоянную сессию COM.

```powershell
cd designer
pip install -e .
python -m designer deck template.pptx brief.txt out --variants a,b,c
```

Собирает без сервера три варианта колоды (`a` как в шаблоне, `b` плотнее, `c` данные вперёд) в `out/a`, `out/b`, `out/c`: `deck.pptx`, `deck.html`, `deck.pdf`.

HTTP-сервис, нужен для UI и для живого режима:

```powershell
python -m designer serve
```

Поднимает FastAPI на порту `DESIGNER_PORT` (по умолчанию 8090): `POST /design-systems` загружает шаблон, `POST /decks` собирает колоду по брифу, `GET /decks/{id}` отдаёт состояние и находки аудита, `POST /decks/{id}/{вариант}/audit-contextual` и `POST /decks/{id}/{вариант}/fix` — контекстный аудит и починка по выбору человека, `POST /live/slide` — слайд из фрагмента речи, `GET /health` — доступность модели, движка конвертации и скиллов.

Настройки читаются из `config.yaml` (путь в `DESIGNER_CONFIG`, по умолчанию `designer/config.yaml`, файл необязателен), переменные окружения из таблицы ниже перекрывают файл (`designer/src/designer/settings.py`).

Экраны в браузере на `http://localhost:8088`: `#/` презентация по брифу, `#/decks/<id>` генерация на глазах, `#/decks/<id>/edit/<вариант>` правка и выгрузка pptx, PDF, HTML, `#/design-systems` дизайн-системы из pptx (палитра, шрифт, кегли, поля, образцы), `#/live` Live-режим, `#/settings` агенты и модели.

### Переменные окружения

| Переменная | Сервис | По умолчанию | Назначение |
|---|---|---|---|
| `DESIGNER_LLM_URL` | designer | `http://127.0.0.1:1234/v1` | адрес OpenAI-совместимого сервера модели |
| `DESIGNER_LLM_MODEL` | designer | `qwen/qwen3.8-27b` | имя модели на этом сервере |
| `DESIGNER_LIVE_LLM_URL`, `DESIGNER_LIVE_LLM_MODEL` | designer | пусто, берутся основные | отдельная модель для слайда из речи (`POST /live/slide`), когда нужна более быстрая |
| `DESIGNER_LLM_PARALLEL` | designer | `4` | сколько текстовых запросов к модели идёт одновременно (текст слотов, аудит слайдов); сервер модели поднимается с тем же числом слотов. Запросы с картинками идут строго по одному |
| `DESIGNER_CONFIG` | designer | `config.yaml` | путь к файлу настроек |
| `DESIGNER_SKILLS_DIR` | designer | `designer/skills` рядом с кодом; в образе `/app/skills` | каталог промптов (скиллов) |
| `DESIGNER_DESCRIBE` | designer | `1` | `0` выключает описание слайдов-образцов моделью при импорте шаблона |
| `DESIGNER_PUBLIC_URL` | backend (Java) | `http://localhost:8090` | адрес `designer`, который браузер получает в заголовке CSP для запросов и картинок |
| `DESIGNER_DATA_DIR` | designer | `./data` | каталог пакетов дизайн-систем и колод |
| `DESIGNER_PORT` | designer | `8090` | порт HTTP-сервиса (`python -m designer serve`) |
| `DESIGNER_ALLOWED_ORIGINS` | designer | пусто, CORS выключен | разрешённые источники CORS через запятую |
| `DESIGNER_SOFFICE` | designer | ищется `soffice` в PATH | путь к бинарнику LibreOffice, если его нет в PATH |
| `DESIGNER_CONVERTER` | designer | первый найденный движок | явный выбор движка конвертации: `libreoffice` или `powerpoint` |
| `MODE` | backend (Java) | `demo` | `demo` (текстовый ввод) или `live` (микрофон, нужны модели) |
| `SLIDE_MODE` | backend (Java) | `sketch` | `sketch` (мини-макет кодом), `llm` (зарезервировано под адаптер локальной LLM) или `designer` (сервис `designer`) |
| `PORT` | backend (Java) | `8080` | порт HTTP и WebSocket внутри контейнера |
| `HOST` | backend (Java) | `0.0.0.0` | адрес прослушивания |
| `ALLOWED_ORIGIN` | backend (Java) | `http://localhost:8080` | источник CORS фронтенда |
| `APP_PORT` | compose | `8088` | внешний порт на хосте, пробрасывается на `PORT` в контейнере |
| `DB_URL` | backend (Java) | обязателен, умолчания нет | адрес PostgreSQL (`compose.yaml` ставит `jdbc:postgresql://db:5432/voicedeck`) |
| `DB_USER` | backend (Java) | `voicedeck` | пользователь БД |
| `DB_PASSWORD` | backend (Java) / compose | `local-development-only` | пароль БД и Postgres-контейнера |
| `MODEL_CONFIG` | backend (Java) | `models/config.json` | путь к конфигу моделей распознавания и VAD |
| `EMBEDDING_BACKEND` | backend (Java) | `ollama` | бэкенд эмбеддингов; `disabled` выключает семантическую сегментацию |
| `EMBEDDING_URL` | backend (Java) | `http://127.0.0.1:11434/v1` | адрес сервера эмбеддингов |
| `EMBEDDING_MODEL` | backend (Java) | `bge-m3-embed` | имя модели эмбеддингов |
| `EMBEDDING_DIMENSION` | backend (Java) | `1024` | размерность вектора эмбеддинга |
| `LLM_URL` | backend (Java) | `http://127.0.0.1:8000/v1` | адрес встроенной LLM для `SLIDE_MODE=llm`: адаптер есть, в текущем сценарии не используется |
| `LLM_MODEL` | backend (Java) | `deckgen` | имя модели для `SLIDE_MODE=llm` |
| `LLM_FALLBACK_MODEL` | backend (Java) | `deckgen-small` | запасная модель при сбое основной |
| `DESIGNER_URL` | backend (Java) | пусто, интеграция выключена | адрес сервиса `designer` для `SLIDE_MODE=designer` |
| `DESIGNER_DESIGN_SYSTEM_ID` | backend (Java) | пусто | id дизайн-системы `designer` по умолчанию для сессии |

### Примеры

В `examples/` девять колод по одному брифу (`examples/brief.txt`): три выданных шаблона на три варианта вёрстки. В каждом каталоге `examples/<шаблон>/<вариант>/` лист слайдов `sheet.jpg`, `deck.pdf` и карточка прогона `run.json`; `deck.pptx` и `deck.html` в git не лежат, их собирает заново `python examples/build.py` при поднятом `docker compose`. Замер 2026-09-23 на Qwen3.8-27B в LM Studio (RTX 5090): импорт шаблона 79–99 с, три варианта колоды на 10–15 слайдов 150–195 с с контекстным аудитом первого варианта (`examples/build.log`).

### Живой режим как надстройка

При `SLIDE_MODE=designer` Java-сервис вместо встроенного генератора слайдов зовёт `designer`. Каждый зафиксированный смысловой фрагмент речи уходит в `POST /live/slide`; сервис ведёт его через тот же сборщик, что и обычный слайд плана — подбор паттерна (`layout/match.py`), заполнение слайда по фрагменту речи (`plan/writer.speech_to_slide`) и сборку сцены (`layout/scene.py`), только без плана колоды и без файлового экспорта. Пустой заголовок в ответе значит «слайд не нужен» — Java получает 204 и фрагмент остаётся без слайда. Дизайн-система сессии меняется на лету командой `design_system` протокола (`docs/protocol.md`); без выбора слайды идут по последнему загруженному шаблону.

### Ограничения

- Генерация изображений внутри слайда (задача со звёздочкой ТЗ, модель class text-to-image) не реализована.
- Встроенные шрифты шаблона, сжатые PowerPoint алгоритмом MicroType Express внутри контейнера EOT, не извлекаются в TTF или OTF. В pptx шрифт сохраняется сам, слайды клонируются из исходника; в HTML-экспорте такой шрифт остаётся без `@font-face` (`designer/src/designer/parse/assets.py`).
- Картинки слайдов в образе снимает LibreOffice через PDF и `pdftoppm`; шрифт Play из шаблона там подставляется другим, поэтому картинка в браузере и в PowerPoint различаются шириной букв. Сам pptx собран из родных фигур шаблона и открывается как есть.
- Импорт шаблона зовёт модель на каждый слайд-образец по одному (54 образца около двух минут): при нескольких одновременных запросах с картинками локальный сервер модели отвечает иначе, чем по одному, и плашка под фото на образце теряется.
- Контекстный аудит по картинке автоматически считается только для первого запрошенного варианта колоды: на все три варианта в 5 минут он не укладывается. Для второго и третьего его запускает отдельный вызов API по решению человека (`designer/src/designer/pipeline.py`).
- Тип слайда-образца по одной геометрии распознаётся грубо. Описание по картинке (`parse/describe.py`) всегда даёт назначение слайда и флаг «держится на фото», а тип меняет только при уверенности разбора ниже 0,7 — паттерн, который разбор счёл уверенным, но определил неверно, уточнения типа не получит.
- Подложки карточек и номера блоков в некоторых макетах нарисованы в картинке макета, а не фигурами. Такой паттерн берётся только под то число блоков, что в образце (`LayoutInfo.full_bleed_picture`); слайд с диаграммой на таком макете уходит на чистый макет того же мастера.

## Модели и архитектура

* Java 21 / Vert.x; React / TypeScript / Vite. Java раздаёт API и frontend на одном порту.
* GigaAM-v3 **CTC с пунктуацией**, INT8, через sherpa-onnx 1.13.8 в JVM. Одна модель для партиалов и финалов; GPU для текущего профиля не требуется.
* Silero VAD: завершение фраз по паузам. Длинная непрерывная речь обрабатывается с ограничением окна 8 секунд и перекрытием 2 секунды.
* `paraphrase-multilingual-MiniLM-L12-v2`, INT8 ONNX: компактные семантические эмбеддинги, mean pooling и L2-нормализация. Сравниваются последние 5 предложений. Дополнительно используются паузы и дедлайн публикации.
* AudioWorklet: FIR-фильтрация, ресемплинг в 16 кГц, PCM16 mono, пакеты 32 мс. WebSocket передаёт аудио и события с монотонными номерами.
* PostgreSQL + pgvector: журнал событий, эмбеддинги, восстановление истории после reconnect. Сырой звук на диск не записывается.
* Мини-макеты создаются обычным кодом из текста сразу после публикации куска, для каждого куска. Конфигурация `SLIDE_MODE=llm` зарезервирована для существующего адаптера локального OpenAI-совместимого LLM-сервера; для текущего сценария она не используется.

Обычные паузы дают более ранние финалы; партиалы обновляются примерно каждые 0.5 с аудио плюс время инференса. Это не гарантия задержки на любом компьютере. Времена отдельных предложений интерполируются внутри фразы. Границы смысловых фрагментов эвристические и могут требовать правки.

## Проверки

```powershell
# Настоящее аудио из официального комплекта GigaAM, передача в реальном темпе
node scripts/live-smoke.mjs

# Можно передать свой PCM WAV: mono, 16 кГц, signed 16 bit
node scripts/live-smoke.mjs path/to/sample.wav

# Frontend
cd frontend
npm ci
npm run build
npm test
```

`docker compose up --build` включает Java-тесты. Дополнительно из корня:

```powershell
docker run --rm -v "${PWD}/backend:/app" -v voicedeck-maven:/root/.m2 -w /app maven:3.9.9-eclipse-temurin-21 mvn verify
```

Проверены сборка, аудиоресемплинг, сентенизация, порядок событий, ревизии, replay, аутентификация и полный серверный аудиотракт на русской записи. Тест микрофона конкретного пользователя требует его речи и разрешения браузера; контрольная запись не заменяет проверку качества на его устройстве.

`MODE=demo` оставлен для тестирования без весов: вместо звука используется текстовый ввод. Для этого режима есть `node scripts/smoke.mjs`.

## Эксплуатация

* `docker compose logs -f app` — журнал; `docker compose stop` / `start` — остановка и запуск.
* `/health` — режим, модели и хранилище; `/metrics` — скользящие p50/p95/p99 серверных измерений.
* Внешний порт 8088 меняется через `APP_PORT`. В compose он привязан только к 127.0.0.1.
* Токен сессии хранится в `sessionStorage` вкладки. Перезагрузка страницы восстанавливает историю; закрытие вкладки удаляет токен. Экспорт JSON сохраняет результаты, но не является импортом сессии.
* База хранится в Docker volume. Не используйте `docker compose down -v`, если данные нужны.
* Клиент буферизует до 30 секунд звука при обрыве сети. Незавершённая аудиофраза при перезапуске сервера может потеряться; сохранённый текст восстанавливается.
* До production ещё нужны длительные нагрузочные прогоны, измерение WER на ваших записях, настройка смысловых порогов и аккаунты пользователей.

Подробности: [протокол](docs/protocol.md), [профиль моделей](docs/live-models.json), [альтернативные модели](models/README.md).
