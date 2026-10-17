# T4-retest progress (dark-factory/voiceDeck, minimax/MiniMax-M3)

Started: 2026-09-21T00:38:00+03:00
Completed: 2026-09-21T00:50:00+03:00
Git HEAD: d1176bf (T4 commit, pushed)
Status: COMPLETE

## Phase 0 — context loaded ✓
- t3-retest-report.json, t4-impl-report.json, t4-semantic-debug-protocol.md, t3-runner.mjs read
- monolog.wav (12.8 MB, 401.2s) + monolog-meta.json (7 true boundaries)
- .env SEMANTIC_DEBUG=true verified

## Phase 1 — docker rebuild ✓
- image rebuilt 00:40, mvn verify 17.8s
- /health ready in 5s
- SEMANTIC_DEBUG wired (T3 phase1b patch preserved)
- bilateral_gap field confirmed in semantic-debug-t4.jsonl sample

## Phase 2 — runner ✓
- t4-runner.mjs adapted from t3-runner.mjs (only filenames)
- 1ms/packet pacing, 78.1s stream
- 194 events dumped to events-t4.jsonl
- 96 semantic_debug events with bilateral_gap to semantic-debug-t4.jsonl
- offline revise (17 chunks) seen; flushed

## Phase 3 — metrics ✓
- reason: deadline 79.4%, marker 17.6%, flush 2.9% (T3: 69/27.6/3.4)
- chunks: 17 final, words 2/62/161 (identical to T3)
- F1 live 0.8 / offline 0.8 (T3: 0.857 / 0.857), recall 0.857 (T3: 1.0)
- slides 42/42 titled

## Phase 4 — calibration ✓ (KEY FINDING)
- 96 pairs (42 boundary / 54 same-topic)
- ALL THREE signals separable by p25:
  - cosine: median 0.4826 vs 0.5373, effect_size -0.431
  - depth (EMA): median 0.0325 vs -0.0276, effect_size +0.4865 ← BEST
  - bilateral_gap: median 0.4502 vs 0.4189, effect_size +0.4367
- best_signal = depth (EMA) — by Cohen's d
- bilateral_gap does NOT dramatically outperform EMA on bge-m3 96 pairs
- T3 conclusion "depth not separable" was heuristic direction bug; corrected here
- 9/96 candidate decisions (same as T3) — depthFloor=0.12 catches only extremes

## Final
t4-retest-report.json written, status:complete. No code/config changes (T4 is purely additive).
