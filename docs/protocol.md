# Контракт VoiceDeck v1

`POST /api/sessions` → `{id,token,mode}`. Токен 256 бит, в БД хранится SHA-256. Сохраняйте токен: без него восстановление запрещено. Этот localhost-сервис не является системой аккаунтов.

WebSocket `/ws/session`: первый текстовый кадр не позже 5 с:

```json
{"type":"auth","session_id":"uuid","token":"secret","from":0}
```

Сервер отдаёт долговечные события с `seq > from`, затем `{type:"ready",seq,audio_seq,audio_offset,mode,stopped}`. Токен не передаётся через URL. Повторное соединение с той же сессией заменяет старое. Восстановление клиента начинается с последнего **применённого** seq; новая страница с пустым состоянием начинает с нуля.

Бинарный кадр — ровно 1040 байт, little endian:

| Смещение | Формат | Значение |
|---|---|---|
| 0 | uint64 | seq аудиопакета, начинается с 1 |
| 8 | uint64 | абсолютное смещение первого сэмпла |
| 16 | 512 × int16 | PCM16 mono, 16000 Гц |

На Java допустимы только значения ≤ Long.MAX_VALUE. Номер и смещение после reconnect берутся из `ready`. Сервер присылает `audio_ack`, при пропуске — `audio_resync`. Эти управляющие события не входят в долговечный журнал. При перегрузке соединение закрывается с 1013, клиент восстанавливает журнал.

Долговечные события содержат `type, session_id, seq, emitted_at` (Unix milliseconds):

* `final`: `sentence:{id,text,t0,t1}`; времена — мс от аудионачала сессии.
* `chunk`: `chunk:{id,rev,status,reason,sentence_ids,text,t0,t1,updated_at}`, `reason`, `latency_ms`. Поле `reason` дублируется внутри объекта куска (additive, с версии T1a 2026-09-20; старые журналы без него валидны): при `chunk` — причина коммита (`marker`, `size-cap`, `sentences-cap`, `size-target`, `deadline`, `drift`, `drift-emergency`, `flush`, `recovered`), при `chunk_revise` — операция (`merge`, `split`, `offline`, `confirm`).
* `chunk_revise`: `operation`, `replace_ids`, `chunks`. Все удаления и вставки применяются атомарно. Источник текста — исходные предложения. Порядок определяется `t0`.
* `slide`: `slide:{chunk_id,rev,title,bullets,notes,source,t0?,t1?}`. Применять только к совпадающей текущей ревизии куска. `title:null` означает отсутствие слайда. `source:quota` — квота, `extractive-demo` — цитаты деморежима, `local-llm` — модель.
* `stopped`: запись завершена.

`partial`, `ready`, `metrics`, `warning`, `flushed`, `audio_ack`, `audio_resync` не имеют долговечного номера события. Партиал заменяется целиком и очищается при финале. Пропуск долговечного `seq` требует reconnect; уже применённые seq игнорируются.

Команды:

```json
{"type":"text","text":"Только для demo."}
{"type":"flush"}
{"type":"stop"}
{"type":"revise","operation":"split","chunk_id":"uuid","rev":2,"split_at":3}
```

`operation`: confirm / merge / split. `rev` должен быть текущим +1; старые значения игнорируются. Для confirm/merge передавайте `split_at:0`. Split делит перед предложением с указанным нулевым индексом; merge объединяет со следующим по времени. Окно 3 минуты считается от последнего изменения куска.

HTTP с заголовком `Authorization: Bearer TOKEN`:

* `GET /api/sessions/{id}/events?from=SEQ`
* `GET /api/sessions/{id}/snapshot`
* `GET /api/sessions/{id}/export?format=html|json`
* `DELETE /api/sessions/{id}/data`

Readiness: `GET /health`. Метрики: `GET /metrics`. Histogram samples ограничены 4096 значениями на стадию, поэтому `_count` здесь размер скользящего окна, не lifetime counter. HUD хранит последние 1000 задержек кусков сессии. История измерений HUD не восстанавливается после рестарта.
