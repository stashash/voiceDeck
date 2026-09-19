# T-S6 — confirmChunkPass() фаза 2 с look-ahead

**Epic:** E-S · **Risk:** medium · **Pipeline:** solo · **Human gate:** optional
**Зависит от:** T-S3, T-S5

## Контекст

Phase 1 (текущая) — каузальная, решения по прошлому. Phase 2 — смотрит на «будущее»: берёт последний provisional чанк + следующий provisional (если есть) и решает confirm/split/merge. Каждое решение — `chunk_revise` через тот же `event()/apply()/wire()`, что естественно перегенерирует слайд (т.к. `slide` event привязан к `chunk.rev`).

## Что меняется

- `Session.confirmChunkPass()` — новый метод.
- Шедулер в конструкторе: `clock.scheduleAtFixedRate(this::confirmChunkPass, 5000, 5000, MILLISECONDS)` (5 с, как в анализе).
- Логика:
  1. Найти последний `provisional` чанк `c`.
  2. Найти следующий `provisional` чанк `next` (если есть).
  3. Если `c` за последние 5 секунд появился новый `sentence` после его `t1` — НЕ трогать (пусть растёт).
  4. Иначе — собрать блок-эмбеддинги конца `c` и начала `next`:
     - Если `cosine > MERGE_THRESHOLD` и пауза `< 2 с` → `chunk_revise merge` через `revise("merge", source="confirmer")`.
     - Если внутри `c` есть провал (depth на середине > 2× dispersion) → `chunk_revise split`.
     - Иначе → `chunk_revise confirm`.

## Acceptance

- `ConfirmPassTest`: 3 чанка по 100 слов каждый с маленькой паузой → после pass → 1 объединённый.
- `ConfirmPassTest`: чанк с двумя внутренними темами (mid-pause) → split.
- При появлении нового предложения в `pending` — pass не трогает активный чанк.
- Все три операции уходят с `source="confirmer"`, чтобы арбитр T-S7 знал.
- Метрика `confirm_pass_latency` — bounded rolling, как `chunk_latency`.
