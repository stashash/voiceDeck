# T-S5 — Размеры чанков: 60 / 150–250 / 300 / 500

**Epic:** E-S · **Risk:** low · **Pipeline:** solo · **Human gate:** none
**Зависит от:** —

## Контекст

Текущий size-cap 500 слов несовместим со схемой слайда (`{bullets ≤ 5 по ≤ 240}`). Целевой коридор — 150–250 слов.

## Что меняется

`Session.commitIds` и логика tick:

```
MIN_WORDS = 60              # ниже — coalesce с соседом или extend
TARGET_MIN_WORDS = 150      # commit после этого, если depth-score молчит
TARGET_MAX_WORDS = 250      # commit принудительно при превышении
HARD_CAP_WORDS = 300        # никогда не больше
EMERGENCY_CAP_WORDS = 500   # аварийный потолок, как сейчас
```

`commit("size")` срабатывает при `>= TARGET_MIN_WORDS` если depth/deadline не сработали. Coalesce-лимит поднимается до 250. `commit("deadline")` остаётся, но только если `>= MIN_WORDS`.

## Acceptance

- `PipelineTest.shortSpeechContinuationsBecomeOneMeaningfulChunk` — обновить ожидания, добавить кейс с 280-словным монологом (должен split'нуться по размеру).
- Кейс с 50 словами: не коммитится один, coalesce с соседом.
- Кейс с 350 словами: 2 чанка по ~175, не один гигант.
- Все размеры читаются из config (для будущей калибровки).
