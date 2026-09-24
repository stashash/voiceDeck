# T-14. Живой режим: смысловой фрагмент речи уходит в сборщик слайдов

Модель: sonnet. Волна 4. Зависит от слитого T-13 (`POST /live/slide`).

## Цель

Спикер говорит в микрофон. Java-сервис распознаёт речь и режет её на смысловые фрагменты, это уже работает. Теперь каждый зафиксированный фрагмент уходит в сервис `designer`, и в ответ приходит слайд в стиле загруженного шаблона: готовый HTML одного слайда и его сцена. Событие `slide` несёт их браузеру. Экран показа в эту задачу не входит.

## Файлы

Только эти файлы, других не трогать:

- `backend/src/main/java/local/voicedeck/Designer.java` (новый)
- `backend/src/main/java/local/voicedeck/Session.java`
- `backend/src/main/java/local/voicedeck/Main.java`
- `backend/src/test/java/local/voicedeck/DesignerTest.java`, `DesignerSlideEventTest.java` (новые)
- `docs/protocol.md`
- `compose.yaml`, `.env.example`
- `frontend/src/store.ts`, `frontend/src/store.test.ts`

## Что сделать

1. `Designer.java`: клиент `POST {DESIGNER_URL}/live/slide` с телом `design_system_id`, `chunk_text`, `used_pattern_ids`. Ответ 200 несёт `scene` и `html`, ответ 204 означает «слайд не нужен». Время ожидания 8 секунд. Адрес обязан быть локальным, как у `Llm` и `EmbeddingClient` (та же проверка `isLocalAddress`). Переменные: `DESIGNER_URL` (пусто означает выключено), `DESIGNER_DESIGN_SYSTEM_ID`.
2. `Session.generate()`: новый режим `SLIDE_MODE=designer`. Фрагмент уходит в `Designer`, событие `slide` получает прежние поля (`title`, `bullets`, `notes` из сцены: заголовок и тексты блоков) и новые необязательные `pattern_id`, `html`, `source: "designer"`. Квоты «один слайд в 45 секунд» в этом режиме нет. Ответ 204 даёт событие с `title: null`, как у приветствий. Сбой сервиса: предупреждение и повтор через 10 секунд, как у локальной модели сейчас; транскрипт и фрагменты продолжают идти. `used_pattern_ids` это паттерны последних пяти слайдов сессии.
3. Команда WebSocket `{"type":"design_system","id":"…"}` меняет дизайн-систему сессии на лету; по умолчанию берётся `DESIGNER_DESIGN_SYSTEM_ID`.
4. `docs/protocol.md`: новые поля события `slide`, новая команда, режим `designer`.
5. `compose.yaml` и `.env.example`: переменные `DESIGNER_URL` (по умолчанию `http://host.docker.internal:8090`), `DESIGNER_DESIGN_SYSTEM_ID`, значение `designer` для `SLIDE_MODE`.
6. `frontend/src/store.ts`: тип `Slide` получает необязательные `pattern_id` и `html`; редьюсер их сохраняет. Вёрстку экрана не трогать.

## Готовность

Java-тесты идут в контейнере, окна не нужны. Из корня репозитория:

```
docker run --rm -v "${PWD}/backend:/app" -v voicedeck-maven:/root/.m2 -w /app maven:3.9.9-eclipse-temurin-21 mvn -q verify
```

и из каталога `frontend`: `npm ci`, затем `npm test`.

Проверки: `DesignerTest` поднимает локальный HTTP-сервер-заглушку внутри теста и проверяет тело запроса, разбор ответа 200 и 204, отказ для нелокального адреса; `DesignerSlideEventTest` проверяет, что событие `slide` в режиме `designer` несёт `html` и `pattern_id`, а при сбое сервиса сессия продолжает принимать текст; прежние тесты зелёные; тест редьюсера проверяет, что `html` сохраняется.

## Запреты

- Логику сегментации речи не менять: правки в `Session.java` только в `generate()` и рядом с ним, плюс команда смены дизайн-системы.
- Промптов и вызовов модели в Java не добавлять: текст слайда пишет сервис `designer`.
- Сервис `designer` и модели не запускать.
