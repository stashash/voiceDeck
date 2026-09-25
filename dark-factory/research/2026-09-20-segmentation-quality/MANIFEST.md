# Segmentation Quality Iteration — 2026-09-20

Source analysis: webchat session (brent) — разбор Session.java/TextTiling.java + roadmap P0–P3.

## Tasks

| ID | Agent | Что | Зависит от | Статус |
|---|---|---|---|---|
| T0-git | brent/kimi | commit+push текущих правок voiceDeck; сверка voiceDeck_m3 | — | done (commit 15c6751, origin gitverse недоступен) |
| T0b-push | brent/kimi | remote → github.com/stashash/voiceDeck + push | T0 | done (15c6751 → master, ssh) |
| T1a-impl-quick | brent/kimi | маркеры (порог 30 + лексикон), chunkSizeTarget 120/cap предложений, reason в chunk JSON | T0b | done (e92b507, 66/66 тестов, pushed) |
| T1b-impl-embeddings | brent/kimi | sentence-level эмбеддинги, stream-level детектор + valley-confirmation, EMA fix, semantic_debug | T1a | done (8f14ce1, 73/73 тестов, pushed) |
| T2-audio-baseline | brent/kimi | edge-tts монолог 8 тем (401с), baseline метрики | T0 | done: 100% deadline (69/69), offline F1=0.69, p50=1663ms |
| T3-retest | brent/MiniMax | ретест монолога на новом коде, калибровка по semantic_debug, сравнение метрик | T1b, T2 | done: F1 0.69→0.857 (+0.167), recall 0.714→1.0, marker 0%→27.6%; EMA-depth не сепарабельна для bge-m3 на 95 парах |
| T4-impl-bilateral | brent (in-session) | bilateral TextTiling-style cosine-distance в Session.detectBoundary + Text helpers + config + тест | T3 | done (d1176bf, 6 файлов +82/-2, pushed github) |
| T4-retest | brent/MiniMax | rebuild docker, rerun монолог, сравнение трёх сигналов (cosine / depth / bilateral_gap) | T4 | running |

## Reports
- t0-git-report.json
- t0b-push-report.json
- t1a-impl-report.json
- t1b-impl-report.json
- t2-baseline-report.json
- t3-retest-report.json
- t4-impl-report.json
- t4-semantic-debug-protocol.md
- t4-retest-report.json (pending — T4-retest subagent)