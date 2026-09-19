# T-S4 — Replay эмбеддингов из pgvector

**Epic:** E-S · **Risk:** low · **Pipeline:** solo · **Human gate:** none
**Зависит от:** T-S1

## Контекст

`Session` восстанавливает предложения из event log, но не восстанавливает `embeddings` — после рестарта `semantic()` молча пропускается (`embeddings.get(sid) == null`). Видно как «drift умер после рестарта».

## Что меняется

- `Store.embeddingsOf(sessionId)` — новый метод, `SELECT sent_id, embedding FROM embeddings WHERE session_id=?`, парсит pgvector-строку `[0.1,0.2,...]` в `float[]`.
- `Session` конструктор после `apply(...)`: `embeddings.putAll(store.embeddingsOf(id))`.
- Если `EMBEDDING_BACKEND=onnx` — тот же путь (формат векторов в БД одинаковый).

## Acceptance

- Тест: создать сессию, закоммитить 5 предложений, симулировать рестарт (`Session.close()` + новый `Session`), проверить что `embeddings.size() == 5`.
- In-memory mode (без DB) — `embeddings` остаётся пустым после рестарта (как раньше, поведение не ухудшаем).
- Поведение в `semantic()` после рестарта неотличимо от поведения до рестарта.
