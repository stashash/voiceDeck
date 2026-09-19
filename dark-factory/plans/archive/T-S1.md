# T-S1 — Сменить эмбеддер: multilingual-MiniLM → bge-m3 через Ollama

**Epic:** E-S (сегментация) · **Risk:** medium · **Pipeline:** solo · **Human gate:** none
**Зависит от:** — · **Блокирует:** T-S2, T-S3, T-S10, T-S11, T-S12

## Контекст

`paraphrase-multilingual-MiniLM-L12-v2` обучен на paraphrase-задачу: высокий косинус у перефразировок, слабый сигнал для тематической сегментации. На ruMTEB bge-m3 в топе для русского (1024-dim), Ollama уже держит `bge-m3-embed:latest`. Это базовая замена, без неё T-S3 (depth-score) и T-S10 (coalesce) не откалибровать.

## Что меняется

| Файл | Действие |
|---|---|
| `backend/src/main/java/local/voicedeck/EmbeddingClient.java` | NEW. HTTP-клиент на `OLLAMA /v1/embeddings`, loopback/SSRF-проверка по образцу `Llm.java`, размерность из `EMBEDDING_DIMENSION`. |
| `backend/src/main/java/local/voicedeck/Models.java` | Заменить ORT-путь на `EmbeddingClient`. Старый ONNX-код сохранить под `EMBEDDING_BACKEND=onnx` (для отката и тестов). Обновить `embeddingStatus()`. |
| `models/config.json` | `embeddingName: "bge-m3-ollama"`, `embeddingPooling: "none"` (Ollama нормализует сама), убрать `embeddingModel`/`embeddingTokenizer` из ORT-схемы. |
| `docs/live-models.json` | То же самое для синхронизации. |
| `compose.yaml` | Добавить `EMBEDDING_BACKEND`, `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`. |
| `.env.example` | Те же переменные. |
| `backend/src/test/java/local/voicedeck/EmbeddingClientTest.java` | NEW. Юнит: размерность, SSRF-reject, mock HTTP для успешного/ошибочного ответа. |

## Acceptance

- `EMBEDDING_BACKEND=ollama` (default) → `Models.embed(text)` отдаёт 1024-dim `float[]` через Ollama.
- `EMBEDDING_BACKEND=onnx` → старое поведение, 384-dim, через ONNX Runtime + DJL.
- `EMBEDDING_URL` обязан резолвиться в loopback/link-local/site-local, иначе старт падает (как `LLM_URL`).
- `embedding_inference` метрика показывает 20–60 мс на предложение (CPU Ollama).
- `mvn verify` зелёный, новый тест проходит.
- pgvector таблица принимает новые 1024-dim векторы (mixed-dim — нормально для pgvector без индексов).

## НЕ делать в этой задаче

- Не трогать `Session.java` (T-S2/T-S3).
- Не менять `Store.embedding()` (формат `float[]` остаётся, dim-agnostic).
- Не запускать эмбеддинги в `Models` напрямую — только через `EmbeddingClient`.
