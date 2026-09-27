# Voice Editor V2: Implementation Checkpoint

Checkpoint status: **REWORK / preview available, not accepted for release**. At this checkpoint no merge, ready PR, or factory-branch push had occurred. The active plan deliberately stays active. The independent [Judge report](VOICE-EDITOR-V2-judge.md) and [Verifier report](../../scripts/voice-factory-verdict.md) retain the failed voice cases.

## Subsequent User-Authorized Integration

On 2026-09-27 the user explicitly requested commit, push and merge with master after receiving the 5/9 ASR result. Server master at `3eee0b5` is integrated, including layout fixes and refreshed demo data. Its setup/export tooling and ignore rules take priority over older branch deletions. Voice editing and voice-to-slide creation are retained. This Git integration does not change the independent REWORK verdict or certify microphone accuracy; the four known recognition failures remain open.

Integration exposed an incompatibility between older saved editor geometry and the new server margin normalization. The voice override matcher now uses the known template alignment and gives source identity priority only within a tiny coordinate-rounding tolerance, retaining the existing distance bound. Independent review reproduced an overlapping-decoy deletion risk in the first correction; the final correction passes that reproduction, a closer-clone check and an unknown-lineage rejection check.

Merged full-suite run before this final rounding hardening: 711 passed, 28 skipped (`.voice-factory/merge-designer-final-junit.xml`, SHA256 `bc26d4e942e7424dcfaae8884be0a379860c2cb342776657967c4a711c5798d9`). Final export/layout/voice regression suite after hardening: 309 passed, 24 skipped, including 12 overlapping-object cases (`.voice-factory/merge-targeted-junit.xml`, SHA256 `5bbb6b96201265e3b496291eda8a21de9889cbb341ab268ff4cfc6f5b6b86d65`). Frontend rerun: 267 passed, 18 skipped. Reviewer Dirac's bounded integration verdict is PASS. The full suite was not repeated after the final matcher hardening; all modified export and voice-element paths were included in the final focused run. App containers were not restarted for this Git-only integration.

## Identity And Isolation

- Base and verified remote `github/stas`: `f5ea09f685376d0c1c52c9b0005fd1493a4b7def`. The requested stas push was completed before factory implementation; the remote SHA was checked again at delivery.
- Branch: `codex/dark-factory-voice-editor`.
- Code checkpoint: `29d7ca89ff2c14be919c33238b9a459c37c48e6f`. Subsequent report-only commits do not change this tested code.
- Worktree: `C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck`.
- Latest app image: `sha256:7ae1256c334a42758cf7860306535051f1203759efb55f7969cd6a660d01e816`. Final `acceptance-delivery` ran against this image after the code checkpoint.
- Isolated preview 5174, app 8089, designer 8091, separate named volumes. Production app/designer containers on 8088/8090 remained running with their original IDs; production documents were not used for mutations.
- Preview: http://localhost:5174/#/decks/f6c0b2c7e16b42fc857b12f1d5073e64/edit/a . This is an isolated copy, not the user's original deck.

## Implemented

Deterministic generated-deck commands cover text replacement/append/dictation, selection, navigation, formatting, color, dimensions, movement/alignment, layers, background, insertion, duplication/deletion, tables, notes, slide operations and undo. Component-editor command coverage is expanded separately. Literal case and punctuation are preserved; explicit invalid targets cannot silently select another object. [Requirements and command examples](../../docs/voice-editor-v2.md) state format-specific limitations.

Common edits bypass the language model. Free-form rewriting uses the installed local `qwen3.8:27b`, is restricted to one selected text object, has bounded planning and cancellation, and rejects stale writes after newer edits. Cold model preparation is separate from the warm request deadline; the measured warm latency does not certify cold startup or general semantic quality.

The voice console exposes microphone/reconnect/stop/undo, selected target, recognized text and command state. Editor audio retains bounded pre/post-roll and flushes native VAD at stop. The non-editor generation audio path and existing voice-to-slide feature are not redesigned.

## Measured Checks

| Check | Result |
| --- | --- |
| Full designer pytest, preserved JUnit | 705 passed, 27 skipped, 18 deprecation warnings; exit 0 |
| Frontend tests | 267 passed, 18 skipped; exit 0 |
| TypeScript/Vite production build | PASS |
| Docker app build with Maven verify | PASS |
| Final independent transport guards | 5/5 PASS |
| Final holdout + production text + audio invocation | 33 passed, **4 failed**; exit 1 retained |
| Fixed ru135 complete-command PCM replay | **5/9**, including final committed-code replay |
| Identical PCM with immediate stop | **5/9** |
| Same phrases at ru175 | **2/9**, not an improvement |
| Reference two-utterance audio dictation | PASS: production executor, persisted text and live HTML |
| Warm local model rewrite | PASS: 1464 ms total, 1396 ms model; real saved text |
| Deterministic edit during model planning | PASS: 38 ms save; old model write rejected HTTP 409 |
| Cancel model without changing document | PASS: 38 ms request; document unchanged |
| Existing Live creation from text | PASS: local model -> rendered slide, 4417 ms total |
| Existing Live creation from reference PCM | PASS: 151/151 packet acknowledgements, two final speech segments, one rendered slide and one empty non-content result; 6517 ms including the 4824 ms audio |
| Desktop/mobile UI inspection | Typed command changes persisted; preview text visible; 1280 px and 390 px layouts inspected without horizontal overflow |
| Physical microphone and representative user speech | **NOT TESTED** |

Final committed-code replay p95: 32.39 ms parser plus HTTP executor, 67.76 ms including a separate saved-state GET, across 28 mutations including setup. It overlapped a short transcript-only generation smoke, so it is not an isolated benchmark. The verifier's earlier four recognized-audio mutation samples had p95 33.20/53.80 ms respectively. Neither measurement includes ASR, utterance duration, browser rendering or physical capture. No zero-delay claim is made.

The four final failures remain selection, movement, replacement and append recognition. Several also fail direct full-PCM decoding. Do not disguise these as parser successes, repair their transcripts, weaken assertions, or infer human speech accuracy from synthetic eSpeak. The original baseline used a weaker semantic criterion, so its 1/9 is not a comparable complete-command accuracy score.

## Factory Trace

Supervised six-role execution reused the factory role guidance, not its incomplete cron dispatcher. Router/PM and integration were performed in this task. Coder A `01a0e249-53b1-7a51-ac94-643bfdd66352` owned backend operations; Coder B `01a0e249-546b-73a3-a7f8-a622d60993a8` owned component commands. Verifier `01a0e249-550d-7823-b595-89b89aec4aed` owned independent holdouts and audio evidence. Reviewer `01a0e254-cb79-7142-84e4-3e9dd87a1d5a` reported PASS after wrong-target, stale UI, table indexing and preview findings were addressed. Judge `01a0e265-7f26-7a62-91af-f265a33d5d92` evaluates the remaining acceptance failures independently. Delivery is a local checkpoint only; PR-Builder release/merge is withheld.

## Reproduction And Remaining Gate

Use `scripts/start-voice-factory.ps1 -Build`, then the [acceptance commands](../../scripts/voice-factory-README.md). Existing weights are reused read-only; no new neural models are downloaded. Full test command: `python -m pytest -o addopts= -q --junitxml=../.voice-factory/designer-junit.xml` in designer; `npm test` and `npm run build` in frontend. Audio acceptance must currently return nonzero for the retained failures.

Next acceptance work requires representative user recordings, a direct/full-PCM comparison for failed commands, and a justified local-ASR correction or model evaluation if those failures persist. Repeat the fixed corpus, unseen human commands, microphone capture, cancellation and Live regression before asking for a merge. Browser-device permission remains the user's action. This checkpoint does not certify arbitrary image/chart insertion, multi-object semantic layout, full template preview/export fidelity, cold-start SLOs, or noisy-room speech.

Raw artifacts are retained locally in ignored directories; reproducible scripts and concise reports are committed. SHA256 anchors:

| Artifact | SHA256 |
| --- | --- |
| `scripts/voice-factory-output/acceptance-delivery.json` | `0742d62e232339dfa85e8ae5606d626125b90f3e2a0fe7da619018b75ca27a26` |
| `.voice-factory/designer-junit.xml` | `f8a28cdcb4dbe4fc4aef070b6bb7afcf38dac365f28672d2bae4529e0b937c1e` |
| `.voice-factory/model-acceptance.json` | `935814e607763eaf336b431b8bac52087c6547b3dccf7766963017415a5114a3` |
| `.voice-factory/live-generation-pcm.json` | `5a2d904e090d1645be44b83e77f2817a726ce92f2fcf0cb523aea39a41a19fdd` |
| `.voice-factory/live-generation-text.json` | `a309f2162f18f254f0d90910300a562e6a1f542fca4671bd4aa8a83e759c3343` |
