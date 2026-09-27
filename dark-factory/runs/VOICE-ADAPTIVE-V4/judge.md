# Independent Judge: VOICE-ADAPTIVE-V4

**Bounded stage: ACCEPT. Overall voice product: REWORK; release BLOCKED.**
Acceptance covers the current operation registry, semantic/multiple selection,
and bounded atomic layout/style macros. It does not certify the pending final
bundle, physical microphone quality, full product completion, or authorize merge.

Assessed 2026-09-27 in `.factory-worktrees/voice-quality`, branch
`codex/voice-quality-factory`, HEAD `e668c4eac5e7a2fc75caf79212f98f979345e9a9`
plus the current uncommitted diff/new files. Read the V4 plan, delivery and ASR
reports, implementation/tests, acceptance script, and raw artifacts below.
The assessed `frontend/src/stage/voiceOperations.ts` SHA256 is
`60fe21bc4bd516cbd2688b8cc5fd251cc9d0927e25aea6963f42d952167f6e29`.
This assessment uses the replacement grammar, not the earlier prefix guard.

| Current priority | Judgment and evidence |
| --- | --- |
| Registry/routing | ACCEPT. Exhaustive typed capabilities; deterministic style/layout paths avoid the model. The current rewrite grammar consumes the entire suffix; the macro lexer respects quotes. Unsupported nonliteral creation parameters are rejected. Inspected regression cases cover mixed intents and quoted text containing macro separators. |
| Semantic selection | ACCEPT. Current-slide content/type/position/title-size and numbered groups; deterministic ordering; ties return candidates and clear old selection. Integration coverage prevents a subsequent edit from using the former target. This is bounded rule-based selection, not arbitrary semantic understanding. |
| Atomic macros | ACCEPT. Up to six steps and 64 unique targets; in-memory planning precedes one guarded batch. Server checks revision and stable slide identity under the shared edit lock, validates every target before snapshot/persist, preserves native shared-shape restrictions, and avoids no-op history. Tests include concurrent submissions, native PPTX/HTML, and complete single undo. |

No additional must-fix defect was established in the inspected current bounded
implementation. Planck's final recheck was still pending and no V4 final review
artifact was available; this is an independent judgment, not a claim that the
reviewer has approved the latest changes.

| Evidence | Result and limit |
| --- | --- |
| `.voice-factory/voice-adaptive-v4-targeted.xml` | Independently read: 360 cases, 354 passed, 6 skipped, zero failures/errors; includes 116 batch cases. |
| `.voice-factory/voice-adaptive-v4-full-scripts.xml` | Independently read: 987 cases, 813 passed, 165 skipped, 9 failures. Failure identities agree with V3's documented baseline failures: seven CLI-stub/PATH, one path-separator, one settings/environment. Baseline equivalence relies on retained V3 evidence; suite remains NOT GREEN. |
| `.voice-factory/voice-adaptive-v4-interrupted-fixtures.xml` | 25 passed in 193.260 seconds before the reported interruption; remaining heavy-template coverage is incomplete. |
| `.voice-factory/voice-adaptive-v4-batch-acceptance.json` | PASS: invalid second target 422, stale revision/wrong slide/replay 409, persisted two-target batch with other slides unchanged, complete single undo. Script assertions inspected. Batch 37 ms, undo 28 ms are single HTTP samples. |
| Frontend/TypeScript | Latest user handoff: 639 frontend passes, followed by two additional regression cases. Earlier run: 630 passed / 18 skipped and tsc PASS. No final result for the two added cases or final bundle was available to this judge; do not report 641 passes or extrapolate earlier tsc/build success. |
| Browser | User/delivery evidence: typed macro 31 ms and group move 37 ms, actual persisted state, visible iframe changes and undo. Not independently replayed by this judge; these are command-execution samples without ASR, not speech-to-visible p95. |
| `.voice-factory/voice-adaptive-v4-rebuilt-asr.json` | Independently read: FAIL, 5/9 complete commands; select/move/replace/append fail. All six recorded evaluator/parser hashes match current files. One synthetic development speaker; rebuilt runtime identity is operator-declared. The report does not hash or exercise the new V4 registry/selection/macro path. |

Required before closing the final implementation handoff: retain Planck's final
disposition, establish the result of both added regression cases, verify the
final bundle after the routing changes, and reconcile delivery counts/source
identity. Existing backend/API evidence remains relevant to the unchanged batch
contract; it cannot certify a later frontend bundle.

Release must-fixes remain: resolve the failed ASR acceptance gate with retained
comparative evidence; accept a fixed human/holdout/noise corpus covering V4
commands and false activations; validate physical microphone lifecycle; measure
repeated, correlated speech-end-to-visible latency including persistence/undo.
Decoder process isolation/watchdog and broader editor/dictation parity remain
unclosed vision items. No model-quality improvement is established by this stage.

Only this `judge.md` was written, using apply_patch. No application/code changes,
test reruns, model calls, microphone access, runtime mutations, commits or merges.

## Final Handoff Addendum - 2026-09-27

**Bounded stage: ACCEPT; final implementation handoff conditions closed.
Overall voice product: REWORK; release remains BLOCKED.** This addendum supersedes
the earlier pending-review/bundle/test-count caveats, including "do not report
641 passes". It does not supersede the release limitations.

Read updated `delivery.md`, `review.md`, `metrics.json` and both final raw JSON
reports. Current HEAD is `3ff12c5f67d67eb5cff9b933115f4d48d2e9d8de`; the current
operation-registry SHA256 still matches the full hash recorded above.

- `voice-adaptive-v4-frontend-final.json`: independently counted 641 passed,
  18 skipped, zero failed; success=true. All 52 operation-parser cases pass.
  This closes the uncertainty about the two additional regression cases.
- `review.md` records Planck's final APPROVE, all five findings closed, 52 parser
  cases and 44 independent boundary probes, with no remaining actionable blocker.
  The disposition is integrator-recorded. The documented quoted-target comma
  limitation remains a non-blocker with separate selection/rewrite as a workaround.
- Updated delivery/review/metrics record final TypeScript/frontend production
  build and Maven verify PASS, and running Docker `.Image`
  `sha256:e042f4ef4979153c6aa32273c1d3fc0b9e298b687844a1859cfc2152bd35769e`.
  After browser reload, mixed requests were refused; both bold/italic flags were
  API-confirmed on two targets (44 ms), and one undo restored both (34 ms).
  These are reported final-bundle observations, not rerun by this judge or p95.
- `voice-adaptive-v4-final-asr.json`: independently read FAIL, 5/9, with the same
  four failed commands; all six evaluator/parser hashes match current files.
  Its runtime label names the final image but remains operator-declared.
  Synthetic development audio does not cover human microphones or new V4 commands.

Release still requires ASR quality, human/noise/holdout and microphone acceptance,
and correlated speech-end-to-visible latency evidence. The nine baseline suite
failures and interrupted heavy-template coverage remain unchanged limitations.
Only this addendum was written; no reruns, model calls or source edits.
