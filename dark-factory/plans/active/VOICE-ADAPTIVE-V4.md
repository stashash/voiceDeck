# VOICE-ADAPTIVE-V4

Status: priorities 1-3 implemented and verified; overall release blocked by ASR acceptance. Branch: codex/voice-quality-factory.
Implementation commit: 3ff12c5f67d67eb5cff9b933115f4d48d2e9d8de.

## Scope and priority

1. Typed operation registry and capability routing. Keep deterministic commands independent of LLM.
2. Semantic and multiple selection on the current slide. Ambiguity must not mutate the document.
3. Bounded layout/style macros with revision and slide identity guards, one save and one undo.
4. Re-evaluate the existing local ASR separately; never equate typed commands with microphone acceptance.

Keep Live slide creation, legacy dictation, export and ordinary editing behavior intact. Do not touch production ports 8088/8090, root checkout changes, global factory jobs, model weights or main branches. No push or merge.

## Execution

Manager/integrator: registry, macro planner, client and editor integration, independent runtime acceptance.
Backend worker: strict voice-batch API, transactional in-memory validation, tests; no frontend writes.
Selection worker: pure semantic/multiple selection resolver and its tests only.
ASR verifier: bounded current-runtime evaluation and evidence; no model download or service reconfiguration.
Reviewer/judge: inspect actual diffs and verification evidence before acceptance.

## Batch contract

POST /decks/{deck_id}/{variant}/slides/{number}/voice-batch

Request: expected_revision (string), target_slide_id (nonempty string), operations (1..64 unique element IDs).
Each operation: element_id, optional box [x,y,width,height], optional style {size_pt,bold,italic,color,align}, optional fill.
Strict allowlist and type validation. At least one changed field per operation. No arbitrary scripts or LLM-generated document writes.
Validate all targets and operations before any snapshot/persist; preserve native shared-shape restrictions. Revision mismatch returns 409. Successful response is DeckVariantState.

## Gates

- Unit coverage for all registry kinds, semantic ambiguity, literal-text protection, layout bounds and unsupported operations.
- API tests for all-or-nothing rejection, stale revision/slide, persisted geometry/style, exactly one history entry and complete undo.
- Existing frontend and targeted backend suites; compare unrelated baseline failures if full suite is run.
- Browser validation against isolated 8189 runtime; verify saved state and visible preview, including group undo.
- Report ASR separately and do not call the overall voice product release-ready while accuracy gates are unmet.
