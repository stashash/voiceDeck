# T-13. Конвейер и сервис: от шаблона и брифа до файлов, и слайд из фрагмента речи

Модель: sonnet. Волна 3. Зависит от слитых волн 1 и 2.

## Цель

Человек загружает pptx, пишет бриф и за пять минут получает презентацию: видит ход работы по шагам, находки аудита, файлы pptx, HTML и PDF и карточку прогона с версиями скиллов. Тот же сервис отдаёт слайд по фрагменту живой речи: Java-сервис распознавания присылает текст смыслового фрагмента и получает готовую сцену в стиле загруженного шаблона.

## Файлы

Только эти файлы, других не трогать:

- `designer/src/designer/pipeline.py` (новый)
- `designer/src/designer/store.py` (новый)
- `designer/src/designer/api/__init__.py`, `designer/src/designer/api/app.py`, `designer/src/designer/api/schemas.py` (новые)
- `designer/src/designer/__main__.py` (новый)
- `designer/tests/test_pipeline.py`, `designer/tests/api/test_app.py` (новые)

Остальные модули не менять, только звать. Сигнатуры смотреть в коде: `build_package`, `load_package`, `make_plan`, `fill_slots`, `speech_to_slide`, `choose_pattern`, `slot_limits`, `compose`, `build_scene`, `run_checks`, `audit_slide`, `audit_deck`, `export_pptx`, `render_deck`, `convert.to_pdf`, `convert.to_png`, `RunRecorder`.

## Что сделать

1. `store.py`: данные на диске в каталоге из переменной `DESIGNER_DATA_DIR` (по умолчанию `./data`): `design-systems/<id>/` (пакет), `decks/<id>/` (план, инструкции, сцены, находки, файлы, `run.json`). Идентификаторы без пользовательского ввода в путях.
2. `pipeline.py`:
   - `import_template(pptx_bytes, filename) -> DesignSystem`;
   - `generate_deck(ds_id, brief, purpose, audience, slide_count, on_event) -> Deck`: план, для каждого слайда подбор паттерна, лимиты, текст под лимиты, инструкция, сцена; затем детерминированный аудит, экспорт pptx и HTML, PDF и картинки при доступном конвертере, контекстный аудит при доступных картинках. `on_event` получает события шагов: название шага, номер слайда, время. Каждый использованный скилл и время этапа пишутся в `RunRecorder`, итог в `run.json`;
   - сбой модели на одном слайде не роняет колоду: слайд собирается из текста плана без переписывания, событие сообщает об этом;
   - `live_slide(ds_id, chunk_text, used_pattern_ids) -> Scene | None`: `speech_to_slide` с типами, которые есть в дизайн-системе, затем подбор паттерна, инструкция, сцена. Пустой заголовок от скилла означает «слайд не нужен».
3. `api/app.py` (FastAPI):
   - `POST /design-systems` (файл pptx) и `GET /design-systems`, `GET /design-systems/{id}` (манифест), раздача файлов пакета (`assets`, `tokens.css`);
   - `POST /decks` (тело: `design_system_id`, `brief`, `purpose`, `audience`, `slide_count`) запускает генерацию в фоне и сразу отдаёт `deck_id`; `GET /decks/{id}/events` отдаёт ход работы потоком `text/event-stream`; `GET /decks/{id}` отдаёт состояние, сцены и находки; `GET /decks/{id}/files/{name}` отдаёт `deck.pptx`, `deck.html`, `deck.pdf`; `GET /decks/{id}/run` отдаёт карточку прогона;
   - `POST /live/slide` (тело: `design_system_id`, `chunk_text`, `used_pattern_ids`) отдаёт сцену и готовый HTML одного слайда либо `204`, когда слайд не нужен;
   - `GET /health`: доступность модели и конвертера, версии скиллов.
   - CORS только для адресов из переменной `DESIGNER_ALLOWED_ORIGINS`.
4. `python -m designer serve` поднимает сервис на порту из `DESIGNER_PORT` (по умолчанию 8090). `python -m designer deck <pptx> <brief.txt> <каталог>` делает то же без сервера.

## Готовность

Из каталога `designer`:

```
python -m pytest tests/test_pipeline.py tests/api
```

Живых вызовов модели нет: клиент подменяется через `httpx.MockTransport`, ответы по схемам плана, слотов и речи готовятся в тесте. Проверки на выданном шаблоне (фикстура `templates`, берётся первый файл): импорт шаблона кладёт пакет в хранилище; генерация на пять слайдов даёт `deck.pptx`, который открывается python-pptx и содержит пять слайдов, `deck.html` с пятью секциями, `run.json` с версиями скиллов `plan-deck` и `fill-slots`; события приходят по порядку и заканчиваются событием готовности; сбой модели на одном слайде не роняет колоду; `POST /live/slide` отдаёт сцену с текстом из ответа модели, а при пустом заголовке `204`; путь с `..` в имени файла отклоняется.

## Запреты

- Окна на экране не открывать: конвертер в тестах подменять, настоящий не звать.
- Модели в LM Studio не загружать, живых вызовов не делать.
- Полный набор тестов не гонять, только свои файлы.
