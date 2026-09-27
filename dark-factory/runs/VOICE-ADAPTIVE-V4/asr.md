# VOICE-ADAPTIVE-V4: ASR Verifier

Date: 2026-09-27. Verdict: **FAIL / recognition release gate remains blocked.**
Fresh preserved nine-case synthetic corpus: **5/9 complete commands**, exit **1**.
A bounded replay-only comparison with zero appended silence also scored **5/9**,
exit **1**. Neither result is human microphone acceptance or V4 editor acceptance.

## Scope and provenance

- Workspace: `C:/Users/Admin/dev/project/voiceDeck/.factory-worktrees/voice-quality`.
- Branch at evaluation: `codex/voice-quality-factory`; HEAD `e668c4eac5e7a2fc75caf79212f98f979345e9a9`.
- Read V3 `review.md`, `judge.md`, `delivery.md`, `knowledge.md`, the final-image raw report, evaluator/transport/README, preserved manifest and `compose.voice-quality.yaml`.
- Verified existing audio root: `C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck/scripts/voice-factory-output/audio`. It exists as a normal directory; all nine referenced WAV hashes, PCM16/mono/16 kHz format and golden parser slots validated before and after replay.
- Corpus: `espeak-ng-ru135-preserved`, one synthetic eSpeak NG 1.52.0 ru135 development speaker, zero human or holdout speakers.
- Corpus SHA256: `84fc89d6ac84d2b23f87b801256561d30ca3804104b0412a1e7e928bee952e79`.
- Exact manifest SHA256: `54c0d23dbabf3a3fcc22618e6bb28b7ea5bc8890493039147131de599a300da5`.
- Endpoint: `http://127.0.0.1:8189`; health before/after: ready, live, sherpa-onnx, audio_stored=false.
- The existing evaluator and transport were invoked unchanged. The ignored run wrapper only prefixes disposable snapshot directories with the unique v4 label and records before/after hashes. This avoids the evaluator's ordinary unlabelled `asr-eval-*` directories.
- Source hashes, manifest, mounted config and inspected backend source did not change during either run. Both reports have identical six evaluator/transport/parser hashes. These also match `.voice-factory/asr-ru135-v3-image-7a0220e.json`.
- Parser `deckVoice.ts` SHA256: `95597f6e14cf0463f8d01effb1b099af34573bc8e431e2b39874418252a5109d`. Integration work elsewhere in the worktree continued; this report does not certify subsequent parser edits, V4 operations or a later rebuilt image.

Raw evidence under `.voice-factory/` (new files, no overwritten evidence):

| Artifact | SHA256 / purpose |
| --- | --- |
| `asr-voice-adaptive-v4-20260927-6c92e1-baseline1000.json` | `fbe7e9d7b4cfdbf17fa0d594f7cbbcb1f362b9cf593a4a1a6ea76eb246bf40f0` |
| `asr-voice-adaptive-v4-20260927-6c92e1-silence0.json` | `e354a0791468cbe7392dba9fbc22a3e44063cabbd4fa14f8d3309f3985739a15` |
| `asr-voice-adaptive-v4-20260927-6c92e1-baseline1000-provenance.json` | Exact argv, exit 1, wrapper/evidence hashes, before/after hashes, no detected source drift |
| `asr-voice-adaptive-v4-20260927-6c92e1-silence0-provenance.json` | Same provenance for the single comparison run |
| `asr-voice-adaptive-v4-20260927-6c92e1.mjs` | Disposable run wrapper; SHA256 `33026443968f1c2c947f617ad3ba11633f60c6d63333742e4e558993d775d6e6` |

## Observed runtime

Read-only Docker inspection succeeded after sandbox access required escalation.
The following identities were checked before and after both evaluations; the
container, image, start time, restart count, application/config/model hashes
were unchanged. This is stronger evidence than the runner's deliberately
operator-declared runtime-label field, but not an in-memory model attestation.

- Container: `52d458cac0a076e9523098a64e75694494affcad4021ae367ea3952a703e98b9`, `voicedeck-voice-quality-app-1`.
- Image: `sha256:7a0220e2f87cbd34e6a5ce8ffcf7b0d004efe8077aff14fcd2af33782cdd0cfc`, matching the final V3 image.
- Started: `2026-09-27T17:34:22.640870375Z`; running; restart count `0`.
- `/app/app.jar`: `ae282698967c7e4a17b2b7ba9ef40320fc576d56cb1b1d6dd42140f26f527c74`.
- `MODEL_CONFIG=/models/config.json`, mounted read-only from `C:/Users/Admin/dev/project/voiceDeck/models`. `/native` is likewise a read-only root-checkout mount.
- Config SHA256: `f35042dc3eecf436b05e5d7e6efded997685d5961a96a188a0672a91a3adf21b`.
- Model: `/models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16/model.int8.onnx`; SHA256 `d5fea8df94263c285e54b21e5774b707c707192d3bdbeffd7b1eb07fb6743b35`.
- Tokens SHA256: `142de7570b3de5b3035ce111a89c228e80e6085273731d944093ddf24fa539cd`.
- Silero VAD SHA256: `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`.
- Installed JVM jar: `sherpa-onnx-jvm-1.13.8.jar`, SHA256 `77b7b047fade4eadada96b568eb92615049aaf1dc317c7244e46c1ea38b9a63b`.
- Installed native jar: `sherpa-onnx-native-lib-linux-x64-1.13.8.jar`, SHA256 `30c93b59381113f9c20aedbbf9fc1ad399158f6bc03dddc0f8934a6e28e069ba`.

Mounted config selects `nemo_ctc`, CPU provider and four ASR threads, with no
separate final model. `Models.java:31-32,79-103` therefore shares the partial/final
recognizer, sets `greedy_search`, and passes 16 kHz samples. Its Silero settings
are hardcoded: threshold 0.5, minimum silence 0.35 s, minimum speech 0.25 s,
window 512 samples, maximum speech 20 s; VAD uses one CPU thread. Editor decoding
uses final inference, with a 5000 ms timeout, not a measured 5000 ms duration.
`Audio.java:55-75,88-91` adds up to 200 ms preceding / 160 ms following context,
preserves completed VAD starts in editor mode and drains VAD on stop.

Those constructor details are source evidence, not live introspection of Java
objects. `Models.java` and `Audio.java` have no diff from V3 source commit
`4ba299ba8ae28f3b9b1d644b5fdb068ca9d70a20`, associated by V3 with this image.
Startup includes warm-up calls, but inter-run load and cache state were not
controlled. Neither run is claimed as cold-start or a controlled warm benchmark.

## Results and failed transcripts

| Case | Exact gold transcript | Raw ASR, 1000 ms silence | Raw ASR, 0 ms silence | Complete command |
| --- | --- | --- | --- | --- |
| select | Выбери элемент один | Вменн | Вменн | FAIL |
| size | Размер шрифта двадцать четыре | Размер шрифта 24 | Размер шрифта 24 | PASS |
| color | Сделай текст красным | Сделай текст красным | Сделай текст красным | PASS |
| move | Вправо на двадцать | Плют. | Плют | FAIL |
| replace | Замени текст на План запуска | За запуска. | За запуска. | FAIL |
| append | Добавь в конец Готово | До конец готово. | До конец готово. | FAIL |
| undo | Отмени | Отмени. | Отмени. | PASS |
| next | Следующий слайд | Следующий слайд | Следующий слайд | PASS |
| previous | Предыдущий слайд | Предыдущий слайд | Предыдущий слайд | PASS |

Per run: four complete-command errors, four normalized-transcript errors, four
action errors, one target error and four argument errors. All failed outputs
parse as `unknown`; `select` loses explicit element 1. These are parser slots,
not observations of editor mutation. Raw punctuation above is preserved; only
the unchanged evaluator's documented normalization is used for transcript scoring.
WER/CER were not calculated. Synthetic complete-command rate is 55.56%, not
human accuracy and not a statistically validated estimate of general quality.

Transport: 785/785 packets acknowledged with 1000 ms silence, 503/503 with 0 ms.
Each of all 18 cases emitted exactly one utterance and a flush; no warning,
resync, error, chunk or slide event occurred. Independent evidence checks passed:
18 distinct utterance UUIDs, text identical to raw events, finite offsets with
`0 <= t0 < t1 <= paddedAudioMs`, matching output SHA256 and unchanged inputs.
All 18 utterance `t0` values are zero; this does not prove acoustically correct
segmentation or explain the recognition failures. Replay cleanup reported no
error and removes only sessions created by this run. No deck executor was loaded.

## Measured timing only

Baseline UTC: `18:00:46.281` to `18:01:12.517`, report interval **26.236 s**.
Zero-silence UTC: `18:02:12.728` to `18:02:30.060`, report interval **17.332 s**.
One run per condition; order fixed baseline then zero-silence, load uncontrolled.

Values below are client milliseconds, rounded to 0.1 ms. `wall` is the existing
`replay_and_scoring_wall_ms` including replay, session work, cleanup and scoring;
`first` is `firstUtteranceFromReplayMs`, measured from paced replay start.

| Case | 1000 ms: wall | 1000 ms: first | 0 ms: wall | 0 ms: first |
| --- | ---: | ---: | ---: | ---: |
| select | 2863.2 | 1677.3 | 1851.2 | 1676.4 |
| size | 3678.7 | 2582.6 | 2742.6 | 2584.5 |
| color | 3045.9 | 1869.2 | 2022.1 | 1868.9 |
| move | 2837.3 | 1806.0 | 1836.7 | 1741.6 |
| replace | 3356.2 | 2296.5 | 2395.5 | 2289.9 |
| append | 2929.8 | 1805.6 | 1950.0 | 1814.0 |
| undo | 2103.5 | 999.5 | 1086.7 | 999.1 |
| next | 2739.7 | 1551.0 | 1730.6 | 1546.1 |
| previous | 2666.6 | 1582.3 | 1704.1 | 1592.9 |

Parser evaluation ranges, rounded to 0.0001 ms: 0.0802-2.4872 ms baseline;
0.0860-2.1422 ms zero-silence (exact values in raw evidence). Baseline
`stopToLastUtteranceMs` is zero for every case because utterances arrived before
stop; the transport clamps this interval at zero. Zero-silence has approximately
43.0 ms for move and 36.8 ms for undo, zero otherwise. These are observed client
stop-to-message intervals, not isolated decoder compute.

The 8.904 s shorter overall replay is consistent with removing one second of
padding per file; it is not an ASR speedup or speech-to-visible improvement.
No speech-end annotations, ASR compute, microphone/capture, execution queue,
document mutation, persistence, visible-render or export timing was measured.
No p95, cross-clock subtraction or real-time factor is claimed.

## Hotwords and next steps

**Hotwords are not a supported tuning knob for this current CTC recognizer.**
The official [sherpa-onnx hotwords documentation](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)
limits this contextual-biasing facility to transducer models with
`modified_beam_search`. The installed-version [v1.13.8 recognizer implementation](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/offline-recognizer-impl.h#L33-L36)
also rejects the base hotword-stream call outside its supported implementations.
The application calls `createStream()` without hotwords and fixes greedy decoding.
Adding a JSON hotword list or changing only a generic beam-search flag is not an
evidence-backed fix for the active GigaAM CTC path. No such change was made.

1. Keep this failed baseline and both raw takes. Zero appended silence is now a measured replay comparison, not an accuracy fix; do not infer microphone endpointing behavior from it.
2. Acquire a separately consented human corpus with fixed development/holdout speakers, manually checked transcripts and speech boundaries. Include short commands, dictation, literal command-like text, negation, numbers, quiet/noisy conditions and non-command audio. This run used no microphone.
3. Before adjusting VAD, repeat full-PCM versus buffered-VAD diagnostics on the pinned runtime in a separately isolated process. Historical `asr-ranges-nocrop-buffered.json` in the old corpus parent shows wrong full-PCM outputs too: select `Вметдин`, move `П лют`, replace `Заменитек план запуска.`, append `До конец готова`. That older artifact was inspected, not rerun; its SHA256 is `4c097fc0278395c0e109cc5ac326060cd50acc1b855f2ddaded19366eec05acd`. It supports testing both acoustics/model and segmentation, not claiming VAD alone explains all failures.
4. If current diagnostics show clipped speech, compare one VAD/context parameter at a time with the same installed weights, labels and parser, retaining all failures and false activations. VAD values are hardcoded in `Models.newVad()`, so editing model JSON alone will not tune them. Do not reduce silence thresholds simply from the replay-duration difference.
5. If full-PCM failures persist on human development speech, plan a separate model/export comparison. Only `model.int8.onnx` is present in the inspected GigaAM directory; a non-int8 or transducer candidate was neither installed nor tested. No winner, quantization benefit or hotword improvement can be claimed here.

## Remaining quality gates and handoff

- Current synthetic regression still fails four of nine; human/noise/holdout accuracy and false-command rates remain unaccepted.
- Actual microphone permissions, device lifecycle, capture gaps, stop/reconnect behavior and consented acoustic tests remain separate gates.
- End-to-end audio -> intended target -> mutation -> persistence -> visible slide needs correlated client timing and annotated speech end, plus repeated trials. Typed commands and a passing transport cannot close it.
- The legacy nine-command corpus does not cover new V4 semantic/multiple selection, layout/style macros or dictation semantics. Integrator must re-run against the final parser and rebuilt runtime, and verify target identity, stale context/revision rejection, save and undo independently.
- V3's decoder-process isolation and broader release blockers are not resolved by this verifier. No frontend/backend product tests or broader V4 acceptance are asserted by this report.

Validation performed: input dry-run before/after, two actual local PCM replays,
raw evidence/hash/event checks, final health and read-only runtime identity/hash
checks. Full exact invocation arrays are in the two provenance files; they
include the verified audio root, endpoint and runtime label. Reproduction must
use a new v4 output filename, since the wrapper/evaluator refuse overwrite.

Writes by this verifier: this report and the five uniquely labelled ignored
files listed above; temporary uniquely labelled v4 WAV snapshots were cleaned
up. No application source, baseline, transcript or model changes; no download,
microphone access, container restart, global/production service changes, commit,
push or merge. Concurrent integrator/worker changes were left untouched.
