# Plans Index — VoiceDeck_m3 (итерация сегментации)

> Итерация 2026-09-18/19 завершена: 14/14 задач, 60/60 backend + 6/6 frontend тестов.

## Active (в работе)

_(пусто)_

## Queue

_(пусто)_

## Completed (эта итерация)

| Task | Closed | Что сделано |
|---|---|---|
| T-S1 | 2026-09-18 23:05 | Эмбеддер MiniLM → bge-m3 через Ollama (`EmbeddingClient`, SSRF-guard, 1024-dim, dual backend) |
| T-S2 | 2026-09-18 23:18 | Блок-эмбеддинги: `joinBlock()` последние 3 предложения |
| T-S4 | 2026-09-18 23:18 | Replay эмбеддингов из pgvector при старте сессии |
| T-S5 | 2026-09-18 23:25 | Размеры чанков 60/200/300/500 из конфига; tick: size-cap/size-target |
| T-S3 | 2026-09-19 01:30 | Depth-score: EMA baseline + dispersion вместо порога 0.3 |
| T-S6 | 2026-09-19 01:30 | confirmChunkPass каждые 5 с: merge look-ahead / split dip / confirm |
| T-S7 | 2026-09-19 01:30 | Арбитр ревизий: source, приоритет human>offline>curator>confirmer>drift |
| T-S8 | 2026-09-19 01:30 | Curator применяет все boundaries; окно 25 → 60 предложений |
| T-S9 | 2026-09-19 01:30 | Дискурсивный лексикон (12 маркеров) → marker-commit |
| T-S10 | 2026-09-19 01:30 | Пороги coalesce/emergency из конфига |
| T-S11 | 2026-09-19 01:30 | LLM-куратор верифицирует depth-кандидатов (verifyBoundaries) |
| T-S12 | 2026-09-19 01:30 | Калибровочный стенд: протокол записи, labeler.html, calibrate.mjs |
| T-S13 | 2026-09-19 01:30 | Офлайн TextTiling-проход после stop (source=offline, арбитр защищает human) |
| T-S14 | 2026-09-19 01:30 | Frontend: badge «Пропущено по квоте» вместо пустого слайда |

## Что НЕ закрыто (сознательно)

* **Калибровка на реальном корпусе** — T-S12 дал инструмент, но 10–15 монологов нужно записать и разметить вручную. Пороги (0.12 / 1.6·σ / 0.55 / 0.65) — стартовые, требуют подтверждения на F1 ≥ 0.7.
* **Live smoke-тест** — `node scripts/live-smoke.mjs` после `docker compose up --build -d` с работающим Ollama (`bge-m3-embed`). Юнит-тесты это не заменяют.
* **WER-замер** — отдельная задача, вне scope этой итерации.

## Архив

`plans/archive/` — все 14 планов этой итерации.
