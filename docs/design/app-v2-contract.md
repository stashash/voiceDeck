# Приложение версии 2: контракт между частями и нарезка работ

Основание: холст `docs/design/canvas/` (23 артборда), принят владельцем 2026-09-24 словами «принято, реализуй в коде».
Карта и решения: `docs/design/brief-app.md`, модель: `docs/model.md`, токены: `docs/design/design-system.md`.

Три потока пишут разные файлы. Этот документ фиксирует, что каждый поток отдаёт остальным. Меняется он только
отдельным решением, иначе потоки разойдутся.

## Поток 1. Сервис designer: API

Владеет файлами: `designer/src/designer/api/app.py`, `api/schemas.py`, `pipeline.py`, `store.py`, `contracts.py`,
`parse/package.py`, `layout/match.py`, новые модули `designer/src/designer/edit.py`, тесты `designer/tests/**`
кроме `tests/llm/`.

### Дизайн-системы

`DesignSystem` (contracts.py) получает поля, все необязательные, со значениями по умолчанию, чтобы старые пакеты читались:

| Поле | Тип | Смысл |
|---|---|---|
| `name` | `str` | имя системы; при импорте из имени файла без расширения, `_` и `-` заменены пробелами |
| `created_at` | `str` | время импорта, ISO 8601 |
| `pattern_overrides` | `dict[str, bool]` | решение автора по образцу: `true` в вёрстке, `false` убран. Нет ключа: действует предложение модели (`needs_images` значит убран) |
| `removal_confirmed` | `bool` | автор нажал «Согласен» под полосой убранных образцов |
| `describe` | `{status: "pending"\|"running"\|"done"\|"failed", done: int, total: int, error: str}` | ход описания образцов моделью |

`Pattern.preview` заполняется при импорте: путь `previews/<pattern_id>.png` внутри пакета (картинка слайда-образца,
640 px). `FontToken` получает `embedded_state: "extracted"|"embedded_not_extracted"|"missing"`: встроенные в pptx
файлы шрифта (`ppt/fonts/*.fntdata`) есть, а `embedded_file` пуст, значит `embedded_not_extracted`.

| Метод и путь | Тело | Ответ | Что делает |
|---|---|---|---|
| `POST /design-systems` | файл pptx (multipart `file`) | `DesignSystem` | разбор без модели (секунды), превью образцов, пакет в хранилище; описание образцов моделью запускается в фоне, `describe.status = "running"`. Повторная загрузка того же файла даёт новый `id` с суффиксом `-2`, `-3`, прежняя система остаётся. Не pptx: 400 `{"detail": "Файл не pptx"}`; не открылся: 400 `{"detail": "Файл повреждён или сохранён не до конца"}` |
| `GET /design-systems` | | `{ids: [...], items: [{id, name, source_file, patterns: int, preview: str\|null, created_at, describe_status}]}` | список, новые сверху. `ids` остаётся для старых клиентов |
| `GET /design-systems/{id}` | | `DesignSystem` | как было, плюс новые поля |
| `PATCH /design-systems/{id}` | `{name?, pattern_overrides?, removal_confirmed?}` | `DesignSystem` | правка автора; `pattern_overrides` сливается с прежним |
| `DELETE /design-systems/{id}` | | 204 | удаляет папку системы |
| `POST /design-systems/{id}/describe` | | `DesignSystem` | описать образцы заново в фоне; решения автора в `pattern_overrides` не трогает |
| `GET /design-systems/{id}/previews/{pattern_id}.png` | | png | картинка образца |

Вёрстка (`layout/match.py` `fits`) берёт образец по правилу: если в `pattern_overrides` есть ключ, решает он; иначе
как сейчас (`needs_images` значит не брать).

### Презентации

| Метод и путь | Тело | Ответ | Что делает |
|---|---|---|---|
| `GET /decks` | | `{items: [{id, title, design_system_id, slides: int, status, started_at, preview: str\|null}]}` | список презентаций, новые сверху; `preview` это адрес картинки первого слайда варианта `a` или `null` |
| `POST /decks` | как было | как было | по умолчанию `variants = ["a","b","c"]` |
| `GET /decks/{id}` | | как было | план появляется в состоянии сразу после шага `plan`, до вёрстки |
| `GET /decks/{id}/events` | | SSE | как было, плюс событие `slide-image` с `slide_index` и `variant`: картинка слайда готова (`render_spec` сразу после компоновки слайда, если движок конвертации есть) и отдаётся по `GET /decks/{id}/{variant}/slides/{n}.png` |

Правка варианта. Каждая правка пишет прежний `deck.json` в `history/<n>.json`, собирает вариант заново (компоновка
затронутых слайдов, аудит по правилам, pptx, html, pdf, картинки) и отвечает новым `DeckVariantState`.

| Метод и путь | Тело | Что делает |
|---|---|---|
| `PATCH /decks/{id}/{v}/slides/{n}/text` | `{element_id, text}` | текст элемента сцены слайда `n` (с единицы). `element_id` из `scenes[].elements[].id` |
| `POST /decks/{id}/{v}/slides/{n}/pattern` | `{pattern_id}` | собрать слайд на другом образце той же системы |
| `GET /decks/{id}/{v}/slides/{n}/patterns` | | `{items: [{pattern_id, kind, preview, current: bool}]}`: до шести образцов, которые годятся под намерение слайда (`fits`), текущий первым |
| `POST /decks/{id}/{v}/slides/{n}/ask` | `{instruction}` | агент переписывает намерение слайда по просьбе, слайд собирается заново |
| `POST /decks/{id}/{v}/slides` | `{action: "add"\|"copy"\|"delete"\|"move", index: int, to?: int}` | лента слайдов: добавить пустой слайд-список после `index`, копия, удалить, переставить |
| `PATCH /decks/{id}/{v}/notes/{n}` | `{notes}` | заметки докладчика слайда |
| `POST /decks/{id}/{v}/revert` | | вернуть последний `history/<n>.json` |
| `POST /decks/{id}/{v}/fix` | как было | как было |
| `POST /decks/{id}/{v}/rewrite` | `{finding_id}` | замечание модели: агент переписывает слайд замечания с текстом замечания как просьбой |

### Агенты: подключение в API

`app.py` не знает, как устроены агенты: он зовёт модуль потока 2 `designer.agents` (см. ниже) и отдаёт:

| Метод и путь | Ответ |
|---|---|
| `GET /agents` | `designer.agents.list_agents()` |
| `POST /agents/{agent_id}/check` | `designer.agents.check_agent(agent_id)` |
| `GET /settings/agents` | `designer.agents.load_assignments()` |
| `PUT /settings/agents` | тело `{deck, live, describe}` → `designer.agents.save_assignments(...)` |

Клиент модели для задачи берётся только так: `designer.agents.client_for("deck" | "live" | "describe")`. Генерация
колоды, правка слайдов и `/live/slide` перестают звать `LlmClient.from_env()` напрямую.

## Поток 2. Агенты: мост на хосте и выбор агента

Владеет файлами: `scripts/agent_bridge.py` (новый, только стандартная библиотека Python 3.12), `designer/src/designer/agents.py`
(новый), `designer/src/designer/llm/bridge.py` (новый), `designer/tests/llm/**`, `docs/wiki/agenty.md` (новый), строка про
мост в `compose.yaml` (переменная `DESIGNER_AGENT_BRIDGE_URL=http://host.docker.internal:8095` у сервиса designer) и `scripts/start-models.ps1` не трогает.

Мост `scripts/agent_bridge.py` слушает `127.0.0.1:8095` на машине пользователя (сервис в Docker CLI хоста не видит):

| Метод и путь | Тело | Ответ |
|---|---|---|
| `GET /agents` | | `{items: [{id: "claude"\|"codex"\|"cursor-agent"\|"opencode", name, version: str\|null, found: bool, path: str\|null}]}`: поиск в PATH и `--version` |
| `POST /agents/{id}/check` | `{model?}` | `{ok: bool, images: bool\|null, seconds: float, message: str}`: короткий запрос «ответь OK», таймаут 30 с |
| `POST /agents/{id}/complete` | `{system, user, model?, images_png_b64?: [str], timeout_s?}` | `{text: str, seconds: float}` или 502 `{error}`: неинтерактивный запуск CLI; картинки мост пишет во временные файлы и передаёт CLI так, как CLI их принимает |

Команды запуска CLI поток 2 берёт из `--help` каждого CLI на этой машине, а не по памяти.

`designer.agents`:

| Функция | Что отдаёт |
|---|---|
| `list_agents() -> dict` | `{items: [{id, kind: "cli"\|"local", name, detail, found: bool, model: str\|null}]}`: CLI из моста (мост недоступен: пусто и `bridge_error`) плюс модели LM Studio (`GET {llm_url}/models`, без моделей эмбеддингов). `id` у CLI `cli:<name>`, у локальной модели `local:<model>` |
| `check_agent(agent_id) -> dict` | `{ok, images, seconds, message}` |
| `load_assignments() -> dict` / `save_assignments(d) -> dict` | `{deck: agent_id, live: agent_id, describe: agent_id}`; хранится в `data/settings/agents.json`; по умолчанию `local:<DESIGNER_LLM_MODEL>` |
| `client_for(task) -> клиент` | объект с тем же интерфейсом, что `LlmClient`: `complete_json(system, user, schema, images_png=None) -> dict`, `close()`, `model`, `call_durations_ms`. Для `local:` это `LlmClient`, для `cli:` это `llm/bridge.py` `BridgeClient`: просит CLI вернуть только JSON по схеме, выделяет JSON из ответа, при сбое разбора повторяет один раз |

## Поток 3. Фронтенд

Владеет файлами: `frontend/**`. Экраны один к одному по холсту `docs/design/canvas/*.dc.html` и снимкам
`docs/design/canvas/shots/*.png`; тексты брать из артбордов дословно. Токены из `docs/design/design-system.md`.

| Адрес | Экран на холсте |
|---|---|
| `#/` | `Home`, `Home-agent`, `Home-first` (нет систем или агента) |
| `#/decks/<id>` | `Generation`, `Gen-done`, `Gen-error`, `Gen-no-images` по состоянию колоды |
| `#/decks/<id>/edit/<variant>` | `Edit`, `Edit-download` |
| `#/design-systems`, `#/design-systems/<id>`, `#/design-systems/new` | `DS-ready`, `DS-parsing`, `DS-sample` (панель поверх), `DS-model-error`, `DS-new`, `DS-not-pptx`, `DS-broken`, `DS-empty`, `DS-edge` |
| `#/live` | `Live-start`, `Live` (логика сессии из `stage/useSession.ts`, переносится) |
| `#/audience/<сессия>` | `Hall` (как было) |
| `#/settings` | `Settings-cli`, `Settings-local` |

Старые экраны уходят: «Речь» (`main.tsx` `App`), `designer/DeckPage.tsx`, `designer/TemplatePage.tsx`, `stage/StagePage.tsx`.
Адрес сервиса designer как сейчас (`VITE_DESIGNER_URL`).

## Проверка готовности

Готово, когда на поднятом стеке (`docker compose up`, мост запущен на хосте, LM Studio с qwen3.8-27b) в браузере
проходят пути: создать дизайн-систему из pptx и увидеть разбор по частям; создать презентацию с главной и увидеть
ход и слайды; открыть правку, поменять текст, образец, попросить агента, исправить замечание, скачать pptx;
выступить в Live-режиме текстом вместо микрофона; в настройках увидеть найденные CLI, проверить агента и назначить
его на задачу. Проверяю я сам снимками экрана, а не зелёными тестами.
