# T-S7 — Арбитр ревизий с полем source

**Epic:** E-S · **Risk:** medium · **Pipeline:** solo · **Human gate:** none
**Зависит от:** T-S6, T-S8

## Контекст

Сейчас правило «кто первый — тот и прав». LLM-куратор и человек-оператор тихо затирают друг друга. Нужна приоритезация: human > curator > confirmer > drift.

## Что меняется

- `chunk_revise` payload получает `source: "human"|"drift"|"curator"|"confirmer"`.
- `Session.revise()` принимает `source` параметр.
- `coalesce()` и `confirmChunkPass()` зовут `revise(... source="confirmer")`.
- `curate()` зовёт `revise(... source="curator")`.
- `Session.apply()` для `chunk_revise` хранит `source` в `chunks[c.id].source` (новое поле).
- В `revise()`: если `c.source == "human"` и пришедший `source != "human"` — тихий reject + warning.

## Frontend

- `store.ts` — `Chunk` тип расширен полем `source?: string`.
- В reducer: при `chunk_revise` проверять, что `source` приоритет >= текущего; иначе игнорировать (на клиенте это уже не нужно, сервер сам решает, но отражать).

## Acceptance

- Тест: human confirm → curator split → curator дропается, чанк остаётся confirmed.
- Тест: drift coalesce → human split → split выигрывает.
- Тест: две curator-операции подряд применяются обе (нет self-conflict).
- Поле `source` есть во всех chunk_revise events.
