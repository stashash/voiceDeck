# Independent Judge: VOICE-QUALITY-V3

Overall user vision: **REWORK, 3.0/5. Release BLOCKED.**
Scoped implementation: **ACCEPT, 4.0/5.** This accepts the safety/dictation stage;
it does not authorize merge, release or a product-wide completion claim.

Base `5f71f013d9d7c268abba20907f74fd4e2c3b3823`; assessed source/test commit
`4ba299ba8ae28f3b9b1d644b5fdb068ca9d70a20`, branch `codex/voice-quality-factory`.
Final application image: `7a0220e2f87cbd34e6a5ce8ffcf7b0d004efe8077aff14fcd2af33782cdd0cfc`.

| Rubric dimension | Scoped implementation | Full user vision | Reason |
| --- | ---: | ---: | --- |
| Correctness | 4 | 2 | Safety guards and reviewer regressions are supported; four spoken commands still fail recognition. |
| Completeness | 4 | 2 | Bounded plan topics are addressed; human voice acceptance and broader semantic capabilities remain incomplete. |
| Idiomatic | 4 | 4 | Reuses existing hooks, queue, transport, API, locks and persistence conventions. |
| Maintainability | 4 | 4 | Focused helpers and explicit limits; dense lifecycle code and bespoke test scheduling prevent 5/5. |
| Test coverage | 4 | 3 | Strong negative/concurrency coverage; mocked scheduling/devices, 18 skips and no accepted physical-microphone lifecycle. |

Equal weights (0.2 each): the rubric supplies no other weights. These are
probabilistic quality judgments, not success probabilities. Missing broader
features lower the vision score, not the score for the explicitly bounded plan.

The four races in `review.md` are closed; the inspected code and 11 cases in
`voiceIntegrationSafety.test.ts` support that closure. Queue expiry cancels
dependent edits, capture metadata survives queuing, manual Save invalidates old
audio, forced stop wins over graceful flush, and restart waits for finalization.
The verifier's capture-gap fix also has a retained regression. The harness runs
production handlers/hooks/transport/worklet with mocked React scheduling and
external boundaries; it is not a real DOM or physical microphone test.

Directly checked: the targeted XML contains **226 passed, zero failures**; model
evidence records persisted rewrite **2708 ms**, concurrent edit **26 ms** with
stale response **409**, and cancellation **35 ms** without mutation. One warm
sample does not establish p95 or speech-to-visible latency. Source/tests match
the frozen commit, and `git diff --check` against the base passes.

The fresh final-image ASR report is **FAIL: 5/9**, agreeing with four other V3
reports on the same corpus. All six recorded evaluator/parser source hashes
match current files. `select`, `move`, `replace` and `append` fail. Reported exit
code is **1**; the inspected runner returns failure for failed cases. This gate
is not upgraded by parser tests, typed browser commands or a rendered Live slide.

Reported evidence, not rerun by this judge: frontend **382 passed / 18 skipped**,
TypeScript/Maven/build PASS; full Python **871 collected / 9 failed**, all nine
reproduced on clean base. That suite remains **BASELINE_NOT_GREEN**. Latest-image
browser checks demonstrate literal legacy replacement, two-phrase manual Save,
API text matching iframe at revision `b96ba82f4fcd476d994fbba7e1d52d97`, and undo.
They use typed transcripts. Live PCM continuity (71/71 packets, no warnings)
still produced erroneous ASR text and is not recognition acceptance.

Remaining release blockers: failed ASR gate, unaccepted human/noise microphone
quality, and absent end-to-end voice latency acceptance. Lexical number/date
checks do not prove semantic preservation. Decoder process isolation, advanced
semantic groups/layout and second-editor dictation parity are not delivered.

Only `judge.json` and `judge.md` were written. No source/test edits, test reruns,
runtime changes, commit or merge. Human merge decision remains required.
No scenarios calibration directory exists in either checkout; judgment uses
the inspected regression evidence and known failed ASR cases.
