# Verifier Verdict: Partial Acceptance

Measured on 2026-09-27 in the isolated `voice-factory/voiceDeck` worktree, app 8089 and designer 8091. Final app image: `sha256:d79b0612dca31e321bbbf437472eba57db71dd5e0a14384ee51c3918ed8f0609`. The fixed synthetic audio corpus is not fully accepted: four of nine complete Russian commands still fail local recognition. Failures remain failing tests, with no fuzzy parser changes or repaired transcripts.

| Evidence | Result |
| --- | --- |
| Independent parser holdout | 21/21 pass |
| Production executor + persisted generated-deck text integration | 6/6 groups pass |
| PCM/isolated-port guards | 5/5 pass |
| Original ru135 synthetic corpus, final image | 5/9 complete commands pass |
| Identical ru135 WAVs, stop without appended silence | 5/9 complete commands pass |
| Same nine phrases, only eSpeak speed changed to ru175 | 2/9 complete commands pass |
| Supplied reference WAV, two-utterance dictation, persisted text and live HTML | Pass, including stop without appended silence |
| Physical microphone, browser device capture, room/accent accuracy | Not tested |

The final ru135 full test invocation reports 33 passing and four failing Vitest cases; the separate transport suite passes five cases. TypeScript verification with `--noEmit --incremental false` passes. Original voice-to-slide/live generation regression is owned by main and is not claimed by this verifier.

## Concrete Findings

The original `Audio` path removed an additional 58 ms from each completed VAD segment. In exact fixed fixtures, complete native-VAD "Следующий слайд" and "Предыдущий слайд" became truncated words after that crop. Native VAD boundaries also removed leading speech in other clips. A standalone diagnostic reused the installed production Models/Audio and native VAD, comparing full PCM, authoritative VAD samples, the old crop, bounded pre/post-roll, and actual callback time ranges.

Main's editor-only correction preserves a bounded 200 ms pre-roll and 160 ms of already-buffered post-roll, and drains native `Vad.flush()` on stop. Final HTTP replay and direct production Audio diagnostics confirm complete size, color, undo and navigation commands on unchanged fixture hashes. Source/resampled waveforms were checked byte-for-byte against documented `audioop.ratecv`; durations differ only by resampling rounding, and replay does not truncate fixtures.

The four residual ru135 failures are:

| Expected speech | Actual transcript |
| --- | --- |
| Выбери элемент один | Вменн |
| Вправо на двадцать | Плют. |
| Замени текст на План запуска | За запуска. |
| Добавь в конец Готово | До конец готово. |

Several of these also fail direct full-PCM decoding, which isolates residual problems beyond frontend parsing. The baseline report's one semantic pass was an incomplete selection transcript; it is not a complete-command pass. The later harness asserts complete transcripts with punctuation/numeric formatting normalization only. The reference WAV's speaker or synthesis provenance is not independently established; its successful replay is not a human microphone acceptance result.

## Latency

Final ru135 run, 28 mutations including text setup and acceptance commands: parser+executor p95 33.74 ms; including a separate fresh persisted-state GET, p95 53.87 ms. Four mutations originating from recognized audio (font, color, undo and reference dictation): parser+executor p95 33.20 ms; including fresh GET, 53.80 ms. These are client wall times after transcript, not server-only timings, UI rendering latency, ASR compute latency or physical microphone latency. The sample size is small. ASR event timestamps, clip durations and packet counts remain in the raw reports.

## Reproduce And Inspect

Use [voice-factory-README.md](voice-factory-README.md) and `voice-factory-run.ps1`. All raw reports and waveforms are under ignored `scripts/voice-factory-output/`:

- `acceptance-summary.json`: compact report comparison and all final transcripts.
- `acceptance-audio.json`, `asr-ranges-baseline.json`: preserved original baseline.
- `acceptance-audio-nocrop.json`: first production correction.
- `acceptance-audio-final.json`, `acceptance-stop-final.json`, `acceptance-audio-ru175-final.json`: final full pipeline results, actions, before/after state, timings and all ASR events.
- `asr-ranges-final.json`, `asr-ranges-final-runtime.json`: final production speech ranges and exact image identity.
- `audio/manifest.json`, `audio/waveform-check.json`: fixed source corpus hashes, duration and exact conversion checks.

The acceptance API copies a seeded isolated demo deck and verifies its source remains unchanged. No commits were made; the verifier did not modify production parser/API code or mainroot services/data. Generated preview HTML was asserted. Browser pixels/export fidelity and physical microphone acceptance remain separate gates.
