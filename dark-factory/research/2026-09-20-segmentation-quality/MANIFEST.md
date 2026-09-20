# Segmentation Quality Iteration — 2026-09-20

Source analysis: webchat session (brent) — разбор Session.java/TextTiling.java + roadmap P0–P3.

## Tasks

| ID | Agent | Что | Зависит от | Статус |
|---|---|---|---|---|
| T0-git | agentsmits-dev | commit+push текущих правок voiceDeck; сверка voiceDeck_m3 | — | spawned |
| T1a-impl-quick | agentsmits-dev | маркеры (порог 30 + лексикон), chunkSizeTarget 120/cap предложений, reason в chunk JSON | T0 | pending |
| T1b-impl-embeddings | agentsmits-dev | sentence-level эмбеддинги, valley-confirmation, EMA order fix | T1a | pending |
| T2-audio-baseline | agentsmits-dev | русское аудио, docker-стек в voiceDeck_m3, baseline reason-дистрибуция | T0 | pending |
| T3-retest | agentsmits-dev | ретест аудио на новом коде, сравнение метрик | T1b, T2 | pending |

## Reports
- t0-git-report.json
- t1a-impl-report.json
- t1b-impl-report.json
- t2-baseline-report.json (+ events dump)
- t3-retest-report.json
