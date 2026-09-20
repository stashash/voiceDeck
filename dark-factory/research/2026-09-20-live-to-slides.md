# VoiceDeck live → slides: выжимка для dark-factory

**Дата**: 2026-09-20
**Полный отчёт**: `C:/Users/Admin/dev/project/brent/research/2026-09-20-voicedeck-live-to-slides/final.md`
**Метод**: brent AGENTS.md v2 (recall → первичные источники → counter-evidence → атомарные claims)

## TL;DR

- **Текущая сегментация (T-S1..T-S14) — современный гибрид**, который покрывает SOTA-подходы 2024-2026. Конкретные пробелы: нет независимого F1-бенчмарка segmentation, нет instruction-tuned embeddings, verifier работает на depth-score кандидатах (не свободный discovery).
- **Live deck generation не реализован ни одним SOTA-вендором** (Otter/Fireflies/Tactiq — live notes; Gamma/Beautiful.ai — post-hoc). Это инновационное поле.
- **Primary LLM = gigachat3-10b-a1.8b** (нативно русский, MIT, 2.4× throughput vs Qwen3-4B, MMLU_RU 68.33%). **Fallback = qwen3:8b** (уже установлен локально).
- **⚠️ gigachat3-10b-a1.8b НЕ установлен в локальном ollama** (проверено /api/tags 2026-09-20). Нужно `ollama pull` перед итерацией.

## Рекомендация: вариант (C) гибрид

- **Live sketch без LLM** (текущее поведение, без изменений).
- **Post-hoc deck generation** по запросу пользователя ("Сделать презентацию") через двухступенчатый LLM-pipeline: (1) outline на полном session text, (2) per-section slide generation.
- **Опционально позже**: light live-polish только для title (требует решения ollama_max_loaded=1).

### Почему НЕ варианты A и B

| | A: Live updates | B: Post-hoc | **C: Гибрид** |
|---|---|---|---|
| Latency требования | <1.5 сек/слайд | нет | нет (post-hoc) |
| VRAM во время записи | 6-17 GB | 1.3 GB | 1.3 GB |
| Качество слайдов | среднее | высокое | высокое |
| UX-инновационность | высокая | низкая | средняя |
| Сложность кода | средняя | средняя | **низкая** |
| Риск для стека | средний | низкий | **низкий** |

## План верхнего уровня для dark-factory

1. **task-LLM-1**: `ollama pull ai-sage/GigaChat3-10B-A1.8B` + smoke-test JSON-schema через /v1/chat/completions.
2. **task-DECK-1**: `POST /session/:id/generate-deck` endpoint (двухступенчатый LLM: outline → per-slide).
3. **task-UX-1**: frontend "Сделать презентацию" кнопка + progress + editable mode.
4. **task-EVAL-1**: 5 репрезентативных русских сессий, ручная оценка sketch vs LLM-deck (3-Likert), замер latency и VRAM.
5. **task-LIVE-POLISH-1 (опционально)**: title-only polish на лету, lazy-load LLM.

## Критические пробелы (требуют закрытия до коммита)

1. ❌ Нет независимых метрик GigaChat3-10B-A1.8B на структурированной русской генерации (JSON-schema output quality).
2. ❌ Не загружены leaderboards ruMTEB/MERA/ruarena 2025-2026 (DDG bot-detection).
3. ❌ Не проведён hands-on тест GigaChat3 через ollama (модель не установлена).
4. ❌ Не загружены академические работы по LLM-based segmentation 2024-2026.
5. ❌ Не замерена latency LLM.slide() на qwen3:8b через локальный ollama.
6. ❌ Не изучены T-lite / Saiga / ruadapt альтернативы.

## Ключевые цитаты

- **GigaChat3-10B-A1.8B** (github.com/salute-developers/gigachat3): "10B total parameters, with 1.8B active per token; reaches the quality level of Qwen3-4B; ~1.5× faster generation speed, suitable for local use". Лицензия MIT.
- **MMLU_RU 68.33%** (aimodels.fyi): "GigaChat3-10B-A1.8B … offers 2.4x faster request throughput. Choose Qwen3-4B for maximum English quality; choose GigaChat3 if you prioritize speed, multilingual support, or Russian performance".
- **bge-m3** (arxiv 2402.03216): "Multi-Linguality (100+ языков), Multi-Functionality (dense+sparse+multi-vector), Multi-Granularity (до 8192 токенов)".
- **VoiceDeck backend** (Session.java): phase-1 EMA depth-score + phase-2 LLM verifyBoundaries (T-S11) + phase-3 TextTiling bilateral resegmentation (T-S13).

## Ограничения текущего исследования

- **partial статус**: 1 из 5 вопросов имеет полные независимые данные; остальные — vendor-цифры + аналитика.
- Бюджет ~45 мин соблюдён; hands-on latency-тест не выполнен (gigachat3 не установлен).
- Все цифры MMLU/MERA — vendor (Sber) или secondary обзоры, не независимый бенчмарк.

## Файлы

- `C:/Users/Admin/dev/project/brent/research/2026-09-20-voicedeck-live-to-slides/final.md` — полный отчёт.
- `C:/Users/Admin/dev/project/brent/research/2026-09-20-voicedeck-live-to-slides/contract.md` — контракт исследования.
- `C:/Users/Admin/dev/project/brent/research/2026-09-20-voicedeck-live-to-slides/evidence/*.md` — 10 passages с цитатами.
- `C:/Users/Admin/dev/project/brent/research/2026-09-20-voicedeck-live-to-slides/run-package.json` — для ingest в evidence-ledger.
