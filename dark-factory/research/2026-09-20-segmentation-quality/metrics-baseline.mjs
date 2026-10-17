// T2 metrics over events-baseline.jsonl
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const here = p => fileURLToPath(new URL(p, import.meta.url));

const events = fs.readFileSync(here('./events-baseline.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
const meta = JSON.parse(fs.readFileSync(here('./monolog-meta.json'), 'utf8'));

// --- replay chunk state ---
const chunks = new Map(); // id -> chunk
for (const e of events) {
  if (e.type === 'chunk') chunks.set(e.chunk.id, e.chunk);
  if (e.type === 'chunk_revise') {
    for (const id of e.replace_ids ?? []) chunks.delete(id);
    for (const c of e.chunks ?? []) chunks.set(c.id, c);
  }
}
const finalChunks = [...chunks.values()].sort((a, b) => a.t0 - b.t0);

// --- reason distribution (chunk events) ---
const reasons = {};
let chunkEventCount = 0;
const latencies = [];
for (const e of events) if (e.type === 'chunk') {
  chunkEventCount++;
  reasons[e.reason] = (reasons[e.reason] ?? 0) + 1;
  if (typeof e.latency_ms === 'number') latencies.push(e.latency_ms);
}

// --- revise ops ---
const reviseOps = {};
for (const e of events) if (e.type === 'chunk_revise') {
  const k = e.operation + '/' + e.source;
  reviseOps[k] = (reviseOps[k] ?? 0) + 1;
}

// --- status / source ---
const statusDist = {}, sourceDist = {};
const sizes = [];
for (const c of finalChunks) {
  statusDist[c.status] = (statusDist[c.status] ?? 0) + 1;
  sourceDist[c.source] = (sourceDist[c.source] ?? 0) + 1;
  sizes.push((c.text ?? '').split(/\s+/).filter(Boolean).length);
}
const pct = n => +(100 * n / chunkEventCount).toFixed(1);

// --- slides ---
const slideEvents = events.filter(e => e.type === 'slide');
const titled = slideEvents.filter(e => e.slide?.title != null).length;
const quotaSkipped = slideEvents.filter(e => e.slide?.title == null).length;

// --- latency percentiles ---
const pctile = (arr, p) => { const s = [...arr].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : null; };

// --- boundary matching vs ground truth ---
// sentences of concatenated final-chunk transcript with word offsets
const norm = s => s.toLowerCase().replace(/[.,!?;:"«»—–-]/g, ' ').replace(/\s+/g, ' ').trim();
const markerNorm = 'переходим к следующей теме';
// build sentence list: [ {text, wordStart, wordEnd, chunkIdxEnd} ]
const sentences = [];
let wOff = 0;
finalChunks.forEach((c, ci) => {
  const parts = (c.text ?? '').match(/[^.!?]+[.!?]+/g) ?? [c.text ?? ''];
  for (const p of parts) {
    const w = p.split(/\s+/).filter(Boolean);
    sentences.push({ text: p.trim(), wStart: wOff, wEnd: wOff + w.length - 1, chunkEnd: ci });
    wOff += w.length;
  }
});
const markerIdx = [];
sentences.forEach((s, i) => { if (norm(s.text).includes(markerNorm)) markerIdx.push(i); });

// true boundaries = end of each block incl. marker (blocks 1..7); 7 internal boundaries
const trueWords = [];
let acc = 0;
for (const b of meta.blocks) { acc += b.words; if (b.block < meta.blocks.length) trueWords.push(acc); }
// map true word boundary -> nearest sentence idx in recognized text
const trueSentIdx = trueWords.map(tw => {
  let best = 0, bd = Infinity;
  sentences.forEach((s, i) => { const d = Math.abs(s.wEnd - tw); if (d < bd) { bd = d; best = i; } });
  return best;
});

// chunk boundary sentence indices (boundary after chunk i)
const chunkBoundSent = [];
sentences.forEach((s, i) => { if (i + 1 < sentences.length && sentences[i + 1].chunkEnd !== s.chunkEnd) chunkBoundSent.push(i); });

const TOL = 2;
const hitTrue = trueSentIdx.filter(t => chunkBoundSent.some(b => Math.abs(b - t) <= TOL));
const hitChunk = chunkBoundSent.filter(b => trueSentIdx.some(t => Math.abs(b - t) <= TOL));
const recall = trueSentIdx.length ? +(hitTrue.length / trueSentIdx.length).toFixed(3) : null;
const precision = chunkBoundSent.length ? +(hitChunk.length / chunkBoundSent.length).toFixed(3) : null;
const f1 = (recall != null && precision != null && (recall + precision) > 0) ? +(2 * recall * precision / (recall + precision)).toFixed(3) : null;

const result = {
  eventCounts: { total: events.length, chunk: chunkEventCount, chunk_revise: events.filter(e => e.type === 'chunk_revise').length, slide: slideEvents.length, final: events.filter(e => e.type === 'final').length, partial: events.filter(e => e.type === 'partial').length, warning: events.filter(e => e.type === 'warning').length },
  reason_distribution: Object.fromEntries(Object.entries(reasons).map(([k, v]) => [k, { n: v, pct: pct(v) }])),
  revise_ops: reviseOps,
  final_chunks: finalChunks.length,
  status_distribution: statusDist,
  source_distribution: sourceDist,
  chunk_words: { min: sizes.length ? Math.min(...sizes) : null, median: sizes.length ? pctile(sizes, 0.5) : null, max: sizes.length ? Math.max(...sizes) : null },
  latency_ms: { p50: pctile(latencies, 0.5), p95: pctile(latencies, 0.95), n: latencies.length },
  slides: { total: slideEvents.length, titled, quota_skipped: quotaSkipped },
  boundary: {
    tolerance_sentences: TOL,
    true_boundaries_internal: trueWords.length,
    true_boundaries_found_in_text: markerIdx.length,
    chunk_boundaries: chunkBoundSent.length,
    matched_true: hitTrue.length, matched_chunk: hitChunk.length,
    recall, precision, f1,
    true_word_boundaries: trueWords,
  },
};
fs.writeFileSync(here('./metrics-baseline.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
