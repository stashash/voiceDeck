# T-S3 — Depth-score вместо абсолютного порога 0.3

**Epic:** E-S · **Risk:** medium · **Pipeline:** solo · **Human gate:** optional
**Зависит от:** T-S1, T-S2

## Контекст

Абсолютный порог 0.3 взят «из чужого домена» и для MiniLM сидит посреди шума (соседние предложения внутри темы часто дают 0.2–0.5). TextTiling использует depth-score: `depth(s) = baseline − cosine(prev, current)`, где baseline = EMA соседних блоков. Это адаптивно к стилю спикера.

## Что меняется

`Session.semantic()` переписывается:

```
baseline = EMA(косинусы последних ~20 блоков, alpha=0.1)
dispersion = EMA(|cosine - baseline|, alpha=0.1)
depth(s) = baseline - cosine(prev, current)

граница, если:
    depth(s) > max(0.12, 1.6 * dispersion)
    AND cosine(s_prev, s_new) < 0.55      # hard sanity floor (bge-m3 шкала, пересмотр после T-S12)
    AND слов в pending >= 60
```

EMA состояние — два `double` поля в `Session`, обновляются на каждом `semantic()`. Старый 0.3 оставить как аварийный потолок: `cosine < EMERGENCY_THRESHOLD` (default 0.2, берётся из config).

## Acceptance

- `SemanticDepthScoreTest`: 3 кейса — монотонная речь (нет границ), смена темы посередине (1 граница), скачки (распределение шире → больше границ).
- Поведение на монотонном монологе 5 минут — 0–1 граница, не 5+.
- Порог `EMERGENCY_THRESHOLD` читается из config.
- Логи `warning` показывают depth и dispersion (для отладки калибровки).
