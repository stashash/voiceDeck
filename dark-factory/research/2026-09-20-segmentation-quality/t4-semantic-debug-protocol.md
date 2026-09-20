# semantic_debug — wire event schema (T4)

Emitted by the stream boundary detector when `SEMANTIC_DEBUG=true` is set in the environment. Non-durable: delivered only via WS wire frame, not stored in the event log. Purpose: post-hoc calibration of the detector on real bge-m3 streams.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `type` | `"semantic_debug"` | discriminator |
| `sid` | uuid | sentence id that triggered this evaluation |
| `cosine` | number | Text.cosine(prev_sentence_vector, current_sentence_vector) |
| `depth` | number | `emaBaseline − cosine` evaluated BEFORE the EMA update |
| `ema_baseline` | number | EMA of cosine (α=0.1), post-update |
| `ema_dispersion` | number | EMA of `|cosine − ema_baseline|` (α=0.1), post-update |
| `bilateral_gap` | number (T4) | `1 − cosine(mean_left, mean_right)` over `bilateralWindow` vectors on each side of `at` (TextTiling-style). 0 = no separation, 1 = strong topic shift. Independent of EMA: lets calibration compare the two signals on real bge-m3 data. |
| `decision` | string | `"none"` / `"candidate"` / `"confirmed-boundary"` |

## Calibration knobs (read from `models/config.json`)

| Key | Default | Effect |
|---|---|---|
| `depthFloor` | 0.12 | EMA-depth threshold floor |
| `deepDipCosFloor` | 1.0 | absolute cosine floor (1.0 disables; bge-m3 calibration pending) |
| `bilateralWindow` | 2 | vectors averaged on each side for bilateral gap |
| `rollingBufferSize` | 20 | max streamIds span for bilateral lookup |
| `dispersionMultiplier` | 1.6 | multiplier on `emaDispersion` in EMA threshold |
| `bilateralFloor` | 0.12 | cosine-distance floor for the bilateral signal |

## Why both signals

The EMA-depth path is adaptive (α=0.1 on cosine) but heavily autocorrelated: when bge-m3 cosine values cluster tightly, `ema_baseline` shadows them and depth≈0. The bilateral path is non-adaptive: it averages cosine over a small window on each side, so a real topic shift leaves a clean gap even when the global baseline drifts. T3 confirmed EMA-depth is not separable on 95 bge-m3 pairs. T4 emits both so a future calibration pass can pick the better signal per corpus.
