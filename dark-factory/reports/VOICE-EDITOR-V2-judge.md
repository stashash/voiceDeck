# VOICE-EDITOR-V2 Independent Judge

**Verdict: REWORK. Score: 3.4/5. Partially verified; not ready for full release.** The deterministic editing and bounded local-model paths have useful evidence. The failing speech matrix prevents acceptance of reliable, wide-command voice editing. Recommend continued supervised evaluation; no PR, merge, or full-quality/zero-delay claim from this judgment.

Evidence cutoff: 2026-09-27 10:38 UTC, including final checkpoint replay, JUnit, PCM and UI evidence. Worktree: `C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck`; branch: `codex/dark-factory-voice-editor`; base: `f5ea09f685376d0c1c52c9b0005fd1493a4b7def`. Checkpoint: `29d7ca89ff2c14be919c33238b9a459c37c48e6f`; its parent is the stated base and tracked files match HEAD. This report is excluded from that checkpoint. Judge inspected main's checkpoint replay artifact without rerunning tests/models; main reports no application changes since commit. Base pushed to `stas` is recorded by the plan/handoff, not independently rechecked remotely.

| df-judge dimension | Score | Basis |
| --- | ---: | --- |
| Correctness | 3 | Persisted deterministic edits and model race/cancel checks pass; four core ru135 commands still fail recognition. |
| Completeness | 3 | Broad operations exist within both document formats; transcript and reference-PCM generation smoke pass. Reliable editing-audio acceptance across the command range remains incomplete. |
| Idiomatic | 4 | Reuses production parser/executor, edit APIs, locking and stored document contracts. |
| Maintainability | 3 | Extracted executor and strict rewrite boundary help; parallel queues, cancellation epochs and format-specific rules still require integration care. |
| Test coverage | 4 | Negative targets, literal text, undo, table/export, persisted state and PCM generation have substantive checks; main also reports desktop/mobile UI verification. Physical device and representative speech coverage remain missing. |

Equal weights (20% each): `(3 + 3 + 4 + 3 + 4) / 5 = 3.4`, within the skill's rework band. This is a qualitative rubric signal, not a calibrated probability or an override of failed acceptance gates.

| Evidence and provenance | Result and interpretation |
| --- | --- |
| [Text acceptance](../../scripts/voice-factory-output/acceptance-text-verified.json) and final audio report's text groups | 6/6 groups pass: literal text/HTML, invalid targets without writes, style/geometry, append/undo, element lifecycle, notes/background/table. Fresh GET is compared with saved state; seed remains unchanged. |
| Fresh [checkpoint acceptance](../../scripts/voice-factory-output/acceptance-delivery.json) | **FAIL, 5/9 exact commands**, same selection/movement/replacement/append failures on `29d7ca8`; reference dictation PASS and source unchanged. Main reports exit 1, 33 pass/4 fail in 37 Vitest cases and separate transport 5/5 pass. This confirms the editing-audio release blocker on the checkpoint. |
| [Final ru135](../../scripts/voice-factory-output/acceptance-audio-final.json) | **FAIL, 5/9 complete commands**. Selection, movement, replacement and append fail; font, color, undo and navigation pass. |
| [Stop without added silence](../../scripts/voice-factory-output/acceptance-stop-final.json) | **FAIL, 5/9**, same four failures. Stop flush preserves the passing cases, not general speech accuracy. Final packet padding still applies. |
| [Final ru175](../../scripts/voice-factory-output/acceptance-audio-ru175-final.json) | **FAIL, 2/9**, only color and undo pass. Sensitivity to synthetic speaking speed remains substantial. |
| Reference two-utterance dictation in all three final reports | PASS, including stop: command then literal counting phrase reach persisted text and live HTML. Inspected saved-state/response text and preview assertion agree. This uses a harness dictation adapter, not the browser microphone flow. |
| [Local model acceptance](../../.voice-factory/model-acceptance.json), checked against [assertion script](../../scripts/verify-deck-voice-model.mjs) | Warm rewrite persists: 1464 ms total, 1396 ms model. Concurrent deterministic save: 38 ms, stale rewrite rejected with HTTP 409. Cancel: 38 ms, subsequent scenes unchanged. One successful rewrite does not establish broad semantic quality or latency percentiles. |
| Inspected full [designer JUnit](../../.voice-factory/designer-junit.xml) | 732 cases: **705 passed, 27 skipped, 0 failures, 0 errors**, independently counted from XML. XML suite time 268.504 s; main reports CLI duration 268.63 s, 18 warnings and exit 0. Full-suite completion is confirmed; skipped tests remain unexecuted coverage. |
| Other test/build handoff | Final frontend rerun: **267 pass/18 skip**, frontend build PASS; focused backend 79 pass; broader backend 123 pass/5 skip; Docker Maven verify twice pass. These are main's reported results, not independently observed runner logs; overlapping counts must not be summed with the full suite. |
| Inspected final [transcript Live-generation smoke](../../.voice-factory/live-generation-text.json) | PASS, 4417 ms elapsed, source `designer`, one processed chunk and one rendered slide, no warnings. Model 3046 ms, image 1023 ms, first-slide total 4096 ms. [Script](../../scripts/verify-live-generation.mjs) explicitly injects text in this mode; `audioCaptureTested=false`. |
| Inspected [non-editor PCM generation regression](../../.voice-factory/live-generation-pcm.json) | PASS: 4824 ms reference WAV, matching SHA256, 151/151 packets acknowledged, two ASR finals and two processed chunks. One rendered designer slide plus one empty no-content result for the counting phrase; not two rendered slides. Elapsed 6517 ms includes PCM playback; first slide `model_ms=1891`, `image_ms=1308`, `total_ms=3210`. No warnings. Source inspection confirms no editor-mode switch/text injection in `--audio` mode. `audioCaptureTested=false`. |
| Main's browser verification handoff | Desktop 1280 and mobile 390 screenshots inspected by main; typed literal edit persisted and white-on-dark preview verified. Judge did not independently inspect those screenshots or operate the browser. |

I independently matched all nine final ru135 WAV hashes to the actual files, baseline and stop reports, and checked sent/acknowledged packet equality. The [baseline](../../scripts/voice-factory-output/acceptance-audio.json) counted 1/9 under a weaker action-kind criterion: its successful selection transcript omitted the command verb. Final checks require the complete phrase with only punctuation/numeric normalization. Do not report a controlled accuracy gain from 1/9 to 5/9; selection itself is now unrecognized. Specific recovered commands and the retained failures are the defensible observations.

Recomputed nearest-rank p95 from raw steps: **33.74 ms** parser plus executor, **53.87 ms** including fresh GET, over 28 mutations including text setup. Only four mutations originated from recognized audio: corresponding p95 values **33.20/53.80 ms**. This supports the <250 ms post-transcript target on these samples. It excludes utterance duration, ASR, browser rendering, cold model startup and physical microphone latency.

Fresh checkpoint replay records **32.3857/67.7577 ms** for the same latency definitions over 28 mutations including setup. Main reports overlap with a short transcript-generation smoke: retain these observations as concurrent-load timings, not an isolated latency benchmark or an improvement claim.

The [Audio.java](../../backend/src/main/java/local/voicedeck/Audio.java) diff gates native VAD flush and bounded 200 ms pre-roll/160 ms available post-roll to editor mode. [Direct diagnostics](../../scripts/voice-factory-output/asr-ranges-final.json) also fail residual phrases on full PCM, so parser changes alone cannot explain or solve the remaining failures. The [verifier runtime artifact](../../scripts/voice-factory-output/asr-ranges-final-runtime.json) records app image `sha256:d79b0612dca31e321bbbf437472eba57db71dd5e0a14384ee51c3918ed8f0609`. Main identifies current runtime `sha256:7ae1256c334a42758cf7860306535051f1203759efb55f7969cd6a660d01e816` as retaining the same production Models/Audio with frontend-only adjustments. Runtime equivalence is main's attestation; the fresh checkpoint replay independently preserves the same four failures in its inspected artifact.

Role trace, using the [plan](../plans/active/VOICE-EDITOR-V2.md) and supplied handoff:

- **Router/PM, main:** isolated checkout/runtime, scope and release gates. Supervised manual roles; no evidence of an autonomous cron execution cycle. Production 8088/8090 is outside acceptance.
- **Coder A:** generated-deck backend operations, validation and undo/export tests. **Coder B:** component-editor deterministic parsing/operations. Main integrates frontend, queues, model handling and editor audio fix.
- **Verifier:** independent holdouts and PCM replay through production code; publishes raw failures and saved-state assertions. Verifier summary reports 21/21 holdouts and 5/5 transport guards; these do not substitute for the failing audio matrix.
- **Reviewer Dirac:** supplied final PASS on latest code after wrong-target, stale-UI and table-index findings were closed. Inspected strict target tests, synchronous state/preview updates and visible-row conversion are consistent with those fixes; reviewer execution history and browser behavior were not independently replayed here.
- **Judge, this report:** read-only source/artifact appraisal, hash comparisons and latency recalculation. No model invocation, test execution, app/test edit, metrics write or production operation.
- **PR-Builder/delivery:** outside this run; no PR or merge is intended or performed. Any future merge still requires technical acceptance and the human gate.

Remaining release gates and limits:

- Resolve and rerun the failed fixed audio cases without repairing transcripts or weakening assertions; add representative reference recordings across the requested command range. Synthetic eSpeak results neither certify nor quantify human speech accuracy. Physical microphone, AudioWorklet/device capture, room/accent coverage and microphone end-to-end latency are **NOT TESTED**; the requested asynchronous reference-audio scope is respected.
- Full-pytest completion and exact counts are now preserved and inspected. The PCM artifact closes the original non-editor Audio-to-ASR-to-generation regression for this reference clip; it does not establish general speech quality. Main owns final checkpoint/runtime provenance in the delivery report. The failed editing-audio gate remains the release blocker, with no ready PR, merge or factory-branch push intended.
- Main's desktop/mobile spot checks cover the stated typed edit and preview; physical capture, comprehensive browser interaction and end-to-end export fidelity are not certified. Failed transcript assertions stop before executor invocation; they are recognition failures, not independent demonstrations of safe document behavior for every corrupted utterance. Generated-deck free-form edits cover one text object; arbitrary image/chart insertion, grouping and multi-object semantic layout are not certified there, as documented in [scope](../../docs/voice-editor-v2.md).

Artifact SHA256 anchors at cutoff:

| File | SHA256 |
| --- | --- |
| `acceptance-audio-final.json` | `947d9cc3a74beb138c7520a489f13a6f2ea3d99e0f118f7c5d5e76406de0b723` |
| `acceptance-stop-final.json` | `ffd19e97906ff73384102e669f51a46faa9d0e388a56177fa4485e35b8f7b186` |
| `acceptance-audio-ru175-final.json` | `ac11cca2d5b12906af55dbf1f68bf0f9d5f4039224e46d852187e6aa8579e713` |
| `model-acceptance.json` | `935814e607763eaf336b431b8bac52087c6547b3dccf7766963017415a5114a3` |
| `live-generation-pcm.json` | `5a2d904e090d1645be44b83e77f2817a726ce92f2fcf0cb523aea39a41a19fdd` |
| `designer-junit.xml` | `f8a28cdcb4dbe4fc4aef070b6bb7afcf38dac365f28672d2bae4529e0b937c1e` |
| `acceptance-delivery.json` | `0742d62e232339dfa85e8ae5606d626125b90f3e2a0fe7da619018b75ca27a26` |
| `live-generation-text.json` | `a309f2162f18f254f0d90910300a562e6a1f542fca4671bd4aa8a83e759c3343` |
