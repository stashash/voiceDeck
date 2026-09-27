# Local ASR Corpus Evaluation

**Preserved measured baseline: 5/9 complete commands on synthetic ru135.** See
[the original verdict](voice-factory-verdict.md). This is not human accuracy or a
new measurement. The new runner retains that baseline in every report, including
failed runs. It never replaces old assertions or reports.

## Reproduce

Run from the isolated voice-quality worktree with Node >=22.18. No npm install,
model download, cloud credentials or running frontend is required. The runner
loads the existing TypeScript parser through Node's type stripping and a narrow
local import resolver; it never imports the deck executor.

```powershell
node scripts/voice-asr-evaluate.mjs --help
node --test scripts/voice-asr-evaluate.test.mjs scripts/voice-factory-audio.test.mjs
node frontend/node_modules/vitest/vitest.mjs run --root frontend src/stage/voiceQualitySafetyAcceptance.test.ts

# Existing WAVs are read only; do not regenerate them for the baseline.
$corpusDir = 'C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck/scripts/voice-factory-output/audio'
node scripts/voice-asr-evaluate.mjs --manifest scripts/voice-asr-baseline.manifest.json --audio-root $corpusDir --dry-run

# Only against an ALREADY RUNNING isolated local ASR service. Use its actual port.
# Replace the label with the known model/config/image identity and warm/cold state.
node scripts/voice-asr-evaluate.mjs --manifest scripts/voice-asr-baseline.manifest.json --audio-root $corpusDir --base http://127.0.0.1:8089 --run-label ru135-baseline --runtime-label 'operator-recorded model/config/image; warm state unknown' --output .voice-factory/asr-ru135.json
```

Exit 0 means all cases passed, or input validation passed with `--dry-run`.
`VALIDATED_NOT_RUN` is never an ASR pass. Exit 1 means a failed case, invalid input,
timeout or service failure; all attempted cases remain in the denominator.
Reports refuse to overwrite an existing file. Raw events and unmodified ASR
utterances are retained. Test fixtures use a unit impulse and mocked transcripts:
the unit test suite is not recognition evidence.

`--base` accepts an explicit HTTP loopback IP and port, including `[::1]`.
Production/preview ports 8088, 8090 and 5174 are rejected, as are DNS hostnames,
credentials and redirects. The existing `voice-factory-audio.mjs` remains the
PCM transport: authenticated 512-sample frames, acknowledgements, editor mode,
stop/flush, and cleanup of only its new ASR session. Because that helper pins
8089, the runner remaps exactly its HTTP/WS origin to the selected endpoint;
it does not start a proxy/server or duplicate the PCM implementation. This
process-wide adapter is scoped to the sequential standalone runner and restored
after evaluation; do not embed concurrent network tasks in the runner process.
The report records the actual destination. The local server's own deployment
and outbound network policy must be verified separately; the runner cannot
attest what an operator-supplied endpoint does internally.

## Manifest Contract

The checked-in [baseline manifest](voice-asr-baseline.manifest.json) is a complete
example with the original nine exact WAV hashes and manually supplied gold
transcript/action/target/arguments. Corpus SHA256 is
`84fc89d6ac84d2b23f87b801256561d30ca3804104b0412a1e7e928bee952e79`.

- Version 1 requires exactly `schema_version`, `corpus_id`, `corpus_sha256`,
  `speakers`, and `cases`; missing/unknown fields, duplicate JSON keys and invalid
  UTF-8 fail.
- Every speaker declares a stable pseudonymous ID, `human` or `synthetic`,
  `development` or `holdout`, provenance, and consent (`recording-consented`
  for humans, `not-applicable` for synthesis). Use the same ID for the same
  person/voice engine across conditions. A speaker belongs to one split only.
  The tool cannot detect a person intentionally relabeled with a second ID.
- Every case requires `id`, `speaker_id`, `condition`, relative `wav`, full-file
  `sha256`, and `expected` with `transcript`, `action`, `target`, `arguments`.
  WAVs must be PCM signed 16-bit, mono, 16 kHz, nonempty/non-silent, at most 45 s.
  Duplicate IDs, paths, hashes, unconsented human entries, path traversal and
  symlink escapes fail before contacting ASR. Maximum corpus size is 256 MiB.
- `target` always has `{ "slide": null, "element": null }` unless the phrase
  explicitly supplies a one-based number. `null` means implicit context, not an
  observed concrete object ID. Selection commands put their number in target;
  all other production action fields go unchanged into `arguments`.
- Golden slots must match the production parser on the golden transcript at
  validation time. This detects damaged labels or parser drift, but is not an
  independent proof of parser correctness. The separate safety suite supplies
  independent expectations. Model-dependent `ask` is only a parser result;
  semantic rewriting, execution and document state are never evaluated here.
- `corpus_sha256` hashes canonical UTF-8 JSON of the entire manifest without
  that field, recursively sorting object keys and preserving array order.
  Thus it binds labels, provenance, splits, ordering and all WAV hashes.
  `manifest_sha256` additionally hashes the exact source JSON bytes. To obtain
  the digest after deliberately editing a new corpus, run the following, then
  review and record the value. Do not change the preserved baseline.

```powershell
node --input-type=module -e 'import fs from "node:fs/promises"; import {corpusHash} from "./scripts/voice-asr-evaluate.mjs"; console.log(corpusHash(JSON.parse(await fs.readFile(process.argv[1], "utf8"))));' path/to/new-manifest.json
```

## Scores And Timing

Each case needs exactly one complete utterance. Transcript comparison permits
case, whitespace, punctuation formatting and the baseline numeric aliases
one/20/24 in Russian; it does not guess missing words or strip negation.
Decimal punctuation is retained. Action, target, and arguments are checked
separately with exact structural equality; literal text arguments retain case,
punctuation and numbers. This literal requirement is stricter than the old
acceptance's case-insensitive text check, so the historical 5/9 is labeled
historical rather than silently recomputed using a changed metric.

A complete-command pass requires transcript and all three slots. Reports give
complete-command errors, transcript errors and each slot's error count by
source kind + split and by speaker. They never pool a human accuracy rate with
synthetic speech. Missing utterances, duplicate segments and runtime failures
fail cases and count all slots as errors. Full before/after deck state and target
object identity require the existing separate editor acceptance.

Only observed client wall intervals and the transport's actual timings appear:
parser evaluation, replay/scoring wall duration, and the existing replay start
to first/last utterance/ACK/stop measurements when available. File duration is
not annotated speech end. `stopToLastUtteranceMs` is the transport's nonnegative
interval, not ASR compute time. No server/client clock subtraction, sum of p95s,
invented warm state or fabricated execution/visible latency is reported.
ASR compute, microphone, queue, execution, persistence, visible and export
latency remain explicitly unmeasured. Runtime identity is operator-declared;
source/manifest/audio hashes are independently computed by the runner.

## Local A/B Matrix

Use the exact same manifest hash, ordered WAVs, speaker splits, parser hashes,
machine/load, warm-state procedure and repetitions for each pair. Freeze the
holdout before model selection; tune only on development speakers. Record
model artifact hashes, runtime/config/image hashes and device/thread settings
in the runtime label or a local experiment record. Do not substitute a model
name for a hash. Keep failures, timeouts and each repetition, never the best take.

| Pair | Change exactly one factor | Keep fixed / interpretation |
| --- | --- | --- |
| A0 / A1 | Appended silence 1000 -> 0 ms | Same model, WAVs, VAD, decoder, CPU/threads; `--trailing-silence-ms 0` |
| A0 / A2 | GigaAM CTC int8 -> non-int8 export | Same family/version, decoder, VAD and CPU; separate operator-run services |
| A0 / A3 | One VAD threshold | Same weights, decoder, PCM and all other VAD options |
| A0 / A4 | CPU -> supported GPU provider | Same weights/export/VAD; measure resource contention separately |
| Candidate screen | ASR implementation as the treatment | GigaAM RNNT, Qwen3-ASR 0.6B, Parakeet TDT v3 are research candidates, not installed winners |

Changing family/runtime/decoder together is an implementation-level comparison,
not evidence isolating quantization or VAD. Full-PCM versus VAD decoding needs
the existing direct Java diagnostic; this replay runner always exercises the
server's editor/VAD path. Non-sherpa candidates require a separately reviewed
adapter; this runner deliberately rejects a different advertised ASR backend.
It does not install, restart, switch or unload any model. Physical microphone,
human-speaker accuracy, browser rendering, export and Live generation remain
separate acceptance gates.

The new safety test file covers pure context/deletion/dictation/queue contracts.
It does not claim browser integration, one persisted undo transaction, or that
stopping a task rolls back a mutation already committed by the server.

## Verified V3 Run: 2026-09-27

Current branch service at 8189, 17:19:29Z to 17:19:56Z: **FAIL, 5/9, exit 1**.
No transport errors. Historical 5/9 remains independently visible. Exact command:

```powershell
node scripts/voice-asr-evaluate.mjs --manifest scripts/voice-asr-baseline.manifest.json --audio-root C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck/scripts/voice-factory-output/audio --base http://127.0.0.1:8189 --run-label voice-quality-v3-current-8189 --runtime-label 'main-reported-current-branch-build; endpoint8189; live/sherpa-onnx-health-verified; GigaAM-v3-CTC-int8; cpu-4threads; warm-state-unknown; Docker-image-inspection-unavailable' --output .voice-factory/asr-ru135-v3-current-8189.json
```

Evidence: `.voice-factory/asr-ru135-v3-current-8189.json`, SHA256
`d3f5c21b4372eaa0c8254d5532bc8c9df5544324ef7d0b910ab6388ec93c2eb1`.
The preceding old-service evidence files `asr-ru135-v3-runner.json` and
`asr-ru135-v3-final.json` also retain 5/9; none were overwritten.

| Case | Raw transcript | Complete command |
| --- | --- | --- |
| select | Вменн | FAIL |
| move | Плют. | FAIL |
| replace | За запуска. | FAIL |
| append | До конец готово. | FAIL |

Action errors: 4; target errors: 1; argument errors: 4. These are parser slots,
not observed document mutations. All nine raw `editor_utterance` records have
distinct UUIDs, finite `0 <= t0 < t1 <= paddedAudioMs`, and text exactly matching
the reported ASR utterance. Their offsets remain audio offsets, not calibrated
speech-end labels. Every source hash in this report matched the current runner,
unchanged PCM helper and production parser at verification time. HTTP health
was read directly. Docker inspection for the new image was denied by the local
environment, so new image identity remains operator-declared.

Main continued editing `deckVoice.ts` after this replay and timestamp check.
The evidence pins parser SHA256
`2cb6fdbfc8abd45dd67a9ca9068ec55057058ebe6d1f348cd6615024eda968a9`;
the subsequent observed file hash was
`95597f6e14cf0463f8d01effb1b099af34573bc8e431e2b39874418252a5109d`.
This report validates the recorded snapshot and server timestamps, not later
parser changes. Re-run with a new output filename at final integration.

Validation commands and outcomes:

```powershell
# 16 passed: 11 new runner checks and 5 unchanged PCM checks.
node --test scripts/voice-asr-evaluate.test.mjs scripts/voice-factory-audio.test.mjs
# 31 passed: 9 new safety cases plus unchanged holdout/literal suites.
node frontend/node_modules/vitest/vitest.mjs run --root frontend src/stage/voiceQualitySafetyAcceptance.test.ts src/stage/voiceFactoryHoldout.test.ts src/stage/voiceLiteralBoundary.test.ts
# Passed.
node --check scripts/voice-asr-evaluate.mjs
node --check scripts/voice-asr-evaluate.test.mjs
node frontend/node_modules/typescript/bin/tsc --noEmit --incremental false --project frontend/tsconfig.json
```

The independent safety suite exposed a capture gap ending inside a phrase:
intervals `[100,300]` and `[400,500]`, phrase `[150,350]`. Main corrected context
coverage; the unchanged independent assertion now passes. The test does not
replace a browser/microphone acceptance run. No deck executor was invoked,
models installed, services changed, or existing acceptance assertions edited.
