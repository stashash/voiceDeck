# VOICE-EDITOR-V2

## Router

- Base: f5ea09f685376d0c1c52c9b0005fd1493a4b7def (pushed and verified on github/stas).
- Branch: codex/dark-factory-voice-editor.
- Workspace: C:/Users/Admin/.codex/worktrees/voice-factory/voiceDeck.
- Mode: supervised six-role factory. Existing cron/request-file dispatcher is not an executor and has a different project path; it is not enabled by this run.
- Risk: high (document mutation); separate checkout/data, independent review, human merge gate.
- Scope: voice editing, its controls, persistence, cancellation, local inference, and acceptance evidence only. No unrelated generation, research agents, or factory infrastructure changes.
- Production localhost:8088 and its data must remain untouched.
- User clarification: existing voice-to-slide creation/live generation remains available and unchanged. Its improvements are deferred; include a regression smoke, not a redesign.

## PM Requirements

1. Preserve both existing editors; prioritize the generated-deck editor used by the user.
2. Deterministic commands: selection and slide navigation, literal dictation/replacement/append, font size/color/bold/italic/alignment, element positioning/dimensions, insertion/duplication/deletion, undo, notes, background, and table editing where supported by the document format.
3. Resolve explicit targets strictly; invalid targets or unsupported operations must not mutate another object. Preserve dictated case and punctuation. Validate before writing and make each mutation undoable.
4. Common commands bypass the LLM. Measure parser/executor and saved-state latency separately from ASR. Target deterministic command p95 below 250 ms after transcript on the local test setup; report misses rather than hiding them.
5. Free-form edits use the installed local model only. Bounded request time, explicit busy/error state, cancellation, and no stale result overwrites. Do not claim zero latency or quality from model-list responses.
6. Audio acceptance must send real PCM through the running local ASR, execute recognized commands using production code, then assert actual persisted document state and preview/export where applicable. Synthetic replay is identified as such; microphone/room accuracy remains a separate user acceptance gate.
7. Unit/integration regression tests cover invalid inputs, queue/recovery, undo, and literal command-like dictated text. Independent reviewer checks the implementation, Judge checks evidence and remaining gaps.

## Execution

- Main / Router-PM-integrator: generated-deck command frontend, runtime isolation, integration, demonstration.
- Coder A: generated-deck deterministic backend operations and tests (designer edit API only).
- Coder B: component-editor deterministic command coverage and tests (stage parser files only).
- Verifier: audio replay harness and independent acceptance cases (new test files/scripts only).
- Reviewer: independent diff review after implementation; findings must be resolved or disclosed.
- Judge / delivery: evidence-based verdict, reproducible run instructions, branch commit; no automatic merge into stas/master.

## Verification State

Implementation checkpoint complete; acceptance remains REWORK, not ready for merge. Full designer suite: 705 passed, 27 skipped; frontend: 267 passed, 18 skipped. Local-model persistence, cancellation and stale-write checks passed. Existing Live generation passed both transcript and reference-PCM smoke checks; its feature remains unchanged.

The fixed ru135 speech corpus passes only 5/9 complete commands; selection, movement, replacement and append still fail recognition. A successful reference dictation recording does not waive these failures. Physical microphone and representative user speech remain unverified. Keep this plan active until these gates pass. See the independent Judge and delivery reports in dark-factory/reports; no automated merge or ready PR is authorized by this checkpoint.
