# VOICE-QUALITY-V3

## Router

- Request: implement the voice-editing quality research through Dark Factory without breaking other functionality.
- Base: github/master 5f71f013d9d7c268abba20907f74fd4e2c3b3823, fetched 2026-09-27.
- Branch: codex/voice-quality-factory.
- Workspace: C:/Users/Admin/dev/project/voiceDeck/.factory-worktrees/voice-quality.
- Risk: high, document mutation and shared microphone transport.
- Pipeline: supervised Dark Factory cascade. The global df-tick request-file dispatcher is not an executor; its queue, cron, and other projects remain untouched.
- Human gate: required before merging. No automatic master/stas merge or push in this run.
- Scope: voice editor safety, dictation, bounded execution, observability, and local-ASR evaluation. Preserve existing voice-to-slide Live creation and both document formats.

## PM Acceptance

1. Voice commands cannot silently target a different object after a manual context switch during recognition. Ordered voice selection followed by an edit still works.
2. Slide deletion confirmation expires and is bound to the same document, variant, slide identity and revision.
3. Keep existing one-shot/two-utterance replacement compatible. Add explicit multi-utterance dictation with a visible draft, finish/cancel, and safe literal command words; commit once and allow undo.
4. Bound command queue size and age. Stop invalidates pending work; delayed results cannot overwrite newer context. Do not falsely claim that stop undoes committed mutations.
5. Flush pending browser microphone samples before editor stop with a bounded handshake. Shared Live recording must retain compatibility and existing tests.
6. Local semantic rewrite remains scoped; support explicit preservation of numbers and dates with server validation and reject unsupported requests rather than silently damaging content.
7. Report execution latency honestly, distinct from recognition and end-to-end visible latency. Warm/cold model status stays explicit; no unloading another user's model.
8. Add a reproducible local ASR corpus/evaluation contract without falsifying the existing 5/9 synthetic failure or claiming microphone acceptance. Do not install or switch large models globally.
9. Independent tests, code review and evidence-based judge verdict. Frontend, designer, Java/audio and existing Live regression are required where the environment supports them; gaps remain explicit.

## Execution Ownership

- Router/PM/integrator: this task; plan, generated-deck EditPage, useVoiceInput, command queue, integration, run isolation and final delivery.
- Coder A: frontend transport.ts, public/pcm-worklet.js, dedicated transport/worklet tests. No EditPage/useVoiceInput changes.
- Coder B: designer voice-rewrite API/planner tests and narrow content-preservation validation. No frontend edits.
- Verifier C: independent ASR evaluation corpus/runner contract and regression evidence, new scripts/tests only.
- Reviewer: independent final diff review, no implementation.
- Judge: independent evidence/acceptance assessment after review, no implementation.

## Preservation Gates

- Production ports 8088/8090 and the existing preview 5174 stay untouched.
- New preview/data must use separate ports and isolated volumes; do not mutate the user's original deck.
- No unrelated refactors or generation/model-provider rewrites.
- No changed failing-ASR expectations, repaired transcripts, or hidden cloud fallback.
- No completion claim for advanced semantic groups/layout, human microphone quality, or a new ASR winner unless independently demonstrated.

## Current State

Implementation and reviewer rework are committed as 4ba299b. See runs/VOICE-QUALITY-V3 for evidence and delivery limits. Synthetic ASR still fails 4/9 cases; physical microphone acceptance is absent. No autonomous scheduler is running. This plan remains active for the unresolved quality gates, not because workers are silently continuing after delivery.
