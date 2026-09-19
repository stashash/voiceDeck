# T-S8 — Curator: применять все boundaries

**Epic:** E-S · **Risk:** low · **Pipeline:** solo · **Human gate:** none
**Зависит от:** —

## Контекст

`Session.curate()` берёт только `boundaries[0]` — если LLM нашла 4 границы, применяется одна. Окно 180 с отсекает старое. Требование `len ∈ [2, 25]` предложений отбрасывает реальные чанки.

## Что меняется

- `Session.curate()` проходит по списку `boundaries[]` с конца, эмитит серию `chunk_revise` через `revise("split", source="curator")` для каждого индекса. Арбитр T-S7 применит их в правильном порядке.
- Ограничение `[2, 25]` снимается (заменяется на `[2, 10]` — слишком большие chunks и так разобьются по size в T-S5).
- `Llm.boundaries()` уже возвращает sorted unique list — это оставляем, но явно проверяем.

## Acceptance

- `CuratorBoundariesTest`: input с 3 границами → 3 split events.
- `CuratorBoundariesTest`: empty `boundaries: []` → confirm, не split.
- Каждый emitted `chunk_revise` имеет `source="curator"` (для арбитра).
- LLM-вызов кешируется на 20 с, чтобы curator не молотил без конца.
