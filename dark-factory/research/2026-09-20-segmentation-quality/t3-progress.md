# T3 (restart on minimax/MiniMax-M3) — progress

- restart_at: 2026-09-20T23:51:07+03:00
- model: minimax/MiniMax-M3
- reason: prior T3 (kimi-for-coding) produced zero artifacts; docker stack still old (Up 3h, pre-T1b).
- git_head: 8f14ce1 (T1a e92b507 + T1b 8f14ce1 влиты, baseline T2 done)
- plan: rebuild docker with SEMANTIC_DEBUG=true, rerun monolog, measure + calibrate.

## Phases

### Phase 0 — prep ✅
- read t2-baseline-report.json, MANIFEST.md, monolog-meta.json, baseline-runner.mjs
- check git HEAD = 8f14ce1, docker stack Up 3h (image pre-T1b)
- .env: added SEMANTIC_DEBUG=true (но compose.yaml не референсит — env НЕ дошёл до контейнера, verified by `docker exec printenv`)

### Phase 1 — build ✅
- docker compose down/up --build (mvn verify 17.6s)
- /health ready: live + ollama:bge-m3-embed

### Phase 2 — retest ✅ (runner v2, faster pacing 1ms/packet)
- Attempt 1 (real-time 32ms/packet): runner orphaned by OpenClaw after ~21min wall-clock, killed
- Attempt 2 (PACKET_INTERVAL_MS=1): 12570 packets in 75.2s, FLUSHED, offline revise seen, events-t3.jsonl=179 events
- session DELETE = 404 (endpoint missing или session уже gone)
- semantic_debug events = 0 (env wiring bug: compose.yaml не передаёт SEMANTIC_DEBUG в контейнер)

### Phase 3 — metrics ✅
- reason: deadline 76.7% (23), marker 20% (6), flush 3.3% (1)
- revise_ops: merge/drift 13, confirm/confirmer 1, offline/offline 1
- final_chunks: 17, all confirmed, source=offline
- chunk_words: min=2, median=62, max=161
- boundary_live F1 = 0.80 (recall 0.857, precision 0.75)
- boundary_offline F1 = 0.80 (same)
- slides: 36, all titled, 0 quota-skipped
- latency_ms = 0 for all events (faster pacing — wall-clock latency не информативна)

### Phase 4 — calibration ✅ done (no apply)
- semantic-debug-t3.jsonl = 95 events captured after env wiring fix
- boundary (n=42) vs same_topic (n=53) labelled by ±30 words around true block boundaries
- distributions: cosine separates (median 0.483 vs 0.537) but depth does NOT (p25 -0.0627 vs -0.0751, wrong direction)
- proposal.separable = false → НЕ применять depthFloor changes, НЕ менять models/config.json, НЕ коммитить
- hypothesis: ema_baseline tracks local cosine too tightly → depth near 0 for both classes
- events-t3b.jsonl НЕ создан (calibration не применена)

