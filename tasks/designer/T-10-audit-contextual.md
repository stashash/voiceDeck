# T-10. Аудит: контекстные проверки по картинке слайда

Модель: sonnet. Волна 2. Зависит от контрактов и слоя модели (T-04).

## Цель

Человек видит на слайде замечания по смыслу: заголовок называет тему, а не вывод; цифры нет в брифе; значок не про это. Такие проверки делает модель, которая понимает изображения, по картинке слайда. На защите команда показывает, какие проверки детерминированные, а какие контекстные, поэтому у каждой находки стоит её вид.

## Файлы

Только эти файлы, других не трогать:

- `designer/src/designer/audit/contextual.py` (новый)
- `designer/skills/audit-slide/skill.yaml`, `designer/skills/audit-slide/prompt.md` (новые)
- `designer/skills/audit-deck/skill.yaml`, `designer/skills/audit-deck/prompt.md` (новые)
- `designer/tests/audit/test_contextual.py` (новый)

`contracts.py`, `llm/client.py`, `llm/skills.py`, `audit/deterministic.py` не менять.

## Что сделать

1. `audit_slide(scene: Scene, png: bytes, source_text: str, client: LlmClient) -> list[Finding]`. Картинку слайда даёт вызывающий код, рендер в эту задачу не входит. Вопросы из приложения 1 к ТЗ, ответ «да» или «нет» с короткой причиной, схема ответа строится кодом:
   - `context.title_is_conclusion` заголовок содержит вывод, а не просто называет тему;
   - `context.body_matches_title` содержимое соответствует заголовку;
   - `context.one_sentence` слайд пересказывается одним предложением;
   - `context.facts_in_source` все цифры и факты со слайда есть в исходных материалах (`source_text`);
   - `context.has_content` на слайде есть содержание, а не только заголовок;
   - `context.visuals_on_topic` картинки и значки относятся к теме слайда;
   - `context.no_service_text` нет служебного мусора: реплик спикера, кусков промпта;
   - `context.no_typos` текст без опечаток;
   - `context.table_rows_work` все строки таблицы и элементы легенды работают на мысль слайда.
   Ответ «нет» становится `Finding` с `kind="contextual"`, `severity="warning"`, причиной в `message`.
2. `audit_deck(scenes: list[Scene], client: LlmClient) -> list[Finding]`: проверки по всей колоде без картинок, по текстам сцен: `context.one_language` вся колода на одном языке, `context.neighbors_linked` соседние слайды связаны по логике. Находка привязывается к слайду, с которого начинается разрыв.
3. Реестр `CONTEXT_CHECKS`: `id`, вопрос по-русски, уровень (слайд или колода). Он нужен документу AUDIT.
4. Параметры запроса в `skill.yaml`, `reasoning_effort: none`, `temperature: 0`. Ошибка модели на одном слайде не роняет аудит колоды: слайд получает находку `context.unavailable`.

## Готовность

Из каталога `designer`:

```
python -m pytest tests/audit/test_contextual.py
```

Живых вызовов нет, сервер подменяется через `httpx.MockTransport`. Тесты проверяют: картинка уходит в запрос как data URL; ответ «нет» по двум вопросам даёт две находки с нужными `check_id`; ответ «да» по всем вопросам даёт пустой список; сбой сервера даёт `context.unavailable` и не исключение; идентификаторы в реестре уникальны и не пересекаются с идентификаторами детерминированных проверок.

## Запреты

- Промпты в код не зашивать.
- Полный набор тестов не гонять, только свой файл.
