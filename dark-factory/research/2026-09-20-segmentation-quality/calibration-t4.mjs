// T4 calibration — compare cosine, depth (EMA), bilateral_gap separability
// Same labeling scheme as calibration-t3.mjs:
//   - semantic_debug sentence -> word-end offset (from final events)
//   - boundary if word-end within ±NEAR_WORDS of any true block boundary
//   - same_topic otherwise
// KEY QUESTION: which of cosine / depth / bilateral_gap best separates
// boundary from same-topic on bge-m3 with 96 pairs?
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const here = p => fileURLToPath(new URL(p, import.meta.url));

const events = fs.readFileSync(here('./events-t4.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
const semantic = fs.readFileSync(here('./semantic-debug-t4.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const meta = JSON.parse(fs.readFileSync(here('./monolog-meta.json'), 'utf8'));

// 1) build sentence_id -> cumulative word offset map from "final" events (ordered by seq)
const finals = events.filter(e => e.type === 'final').sort((a, b) => a.seq - b.seq);
const sentWordEnd = new Map();
let wOff = 0;
for (const e of finals) {
  const w = (e.sentence.text ?? '').split(/\s+/).filter(Boolean).length;
  wOff += w;
  sentWordEnd.set(e.sentence.id, wOff);
}

// 2) true block-end word offsets
const trueWordBoundaries = [];
let acc = 0;
for (const b of meta.blocks) {
  acc += b.words;
  if (b.block < meta.blocks.length) trueWordBoundaries.push(acc);
}

// 3) for each semantic_debug event, label as boundary or same_topic
const NEAR_WORDS = 30;
const pairs = [];
for (const sd of semantic) {
  const w = sentWordEnd.get(sd.sid);
  if (w == null) continue;
  const isBoundary = trueWordBoundaries.some(tb => Math.abs(tb - w) <= NEAR_WORDS);
  pairs.push({
    sid: sd.sid,
    wordEnd: w,
    label: isBoundary ? 'boundary' : 'same_topic',
    cosine: sd.cosine,
    depth: sd.depth,
    bilateral_gap: sd.bilateral_gap,
    ema_baseline: sd.ema_baseline,
    ema_dispersion: sd.ema_dispersion,
    decision: sd.decision,
  });
}

// 4) distribution stats
function stats(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const pct = p => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return {
    n: arr.length,
    min: +s[0].toFixed(4),
    p25: +pct(0.25).toFixed(4),
    median: +pct(0.5).toFixed(4),
    p75: +pct(0.75).toFixed(4),
    max: +s[s.length - 1].toFixed(4),
    mean: +(arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(4),
  };
}

// 5) Cohen's d effect size for each signal
function cohensD(a, b) {
  if (a.length < 2 || b.length < 2) return null;
  const ma = a.reduce((x, y) => x + y, 0) / a.length;
  const mb = b.reduce((x, y) => x + y, 0) / b.length;
  const va = a.reduce((x, y) => x + (y - ma) ** 2, 0) / (a.length - 1);
  const vb = b.reduce((x, y) => x + (y - mb) ** 2, 0) / (b.length - 1);
  const sp = Math.sqrt(((a.length - 1) * va + (b.length - 1) * vb) / (a.length + b.length - 2));
  if (sp === 0) return null;
  return +((ma - mb) / sp).toFixed(4);
}

const boundaryPairs = pairs.filter(p => p.label === 'boundary');
const sameTopicPairs = pairs.filter(p => p.label === 'same_topic');

const dist = {
  boundary: {
    cosine: stats(boundaryPairs.map(p => p.cosine)),
    depth: stats(boundaryPairs.map(p => p.depth)),
    bilateral_gap: stats(boundaryPairs.map(p => p.bilateral_gap)),
  },
  same_topic: {
    cosine: stats(sameTopicPairs.map(p => p.cosine)),
    depth: stats(sameTopicPairs.map(p => p.depth)),
    bilateral_gap: stats(sameTopicPairs.map(p => p.bilateral_gap)),
  },
};

// separability test: for cosine, boundary should have LOWER cosine (more dissimilar adjacent sents).
//   separable if boundary_p25 < same_topic_p25
// for depth (EMA), boundary should have LARGER depth (deeper dip below baseline). depth = ema_baseline - cosine.
//   separable if boundary_p25 > same_topic_p25 (depth is positive when cosine dips)
// for bilateral_gap, boundary should have LARGER bilateral_gap (1 - cos(mean_left, mean_right)).
//   separable if boundary_p25 > same_topic_p25
const sep = (b, st, direction) => {
  if (!b || !st) return null;
  if (direction === 'lower_is_boundary') return { separable: b.p25 < st.p25, detail: `boundary_p25=${b.p25} vs same_topic_p25=${st.p25}` };
  if (direction === 'higher_is_boundary') return { separable: b.p25 > st.p25, detail: `boundary_p25=${b.p25} vs same_topic_p25=${st.p25}` };
  return null;
};

const separability = {
  cosine: {
    ...sep(dist.boundary.cosine, dist.same_topic.cosine, 'lower_is_boundary'),
    boundary_median: dist.boundary.cosine?.median,
    same_topic_median: dist.same_topic.cosine?.median,
    median_diff: dist.boundary.cosine && dist.same_topic.cosine ? +(dist.boundary.cosine.median - dist.same_topic.cosine.median).toFixed(4) : null,
    effect_size: cohensD(boundaryPairs.map(p => p.cosine), sameTopicPairs.map(p => p.cosine)),
  },
  depth: {
    ...sep(dist.boundary.depth, dist.same_topic.depth, 'higher_is_boundary'),
    boundary_median: dist.boundary.depth?.median,
    same_topic_median: dist.same_topic.depth?.median,
    median_diff: dist.boundary.depth && dist.same_topic.depth ? +(dist.boundary.depth.median - dist.same_topic.depth.median).toFixed(4) : null,
    effect_size: cohensD(boundaryPairs.map(p => p.depth), sameTopicPairs.map(p => p.depth)),
  },
  bilateral_gap: {
    ...sep(dist.boundary.bilateral_gap, dist.same_topic.bilateral_gap, 'higher_is_boundary'),
    boundary_median: dist.boundary.bilateral_gap?.median,
    same_topic_median: dist.same_topic.bilateral_gap?.median,
    median_diff: dist.boundary.bilateral_gap && dist.same_topic.bilateral_gap ? +(dist.boundary.bilateral_gap.median - dist.same_topic.bilateral_gap.median).toFixed(4) : null,
    effect_size: cohensD(boundaryPairs.map(p => p.bilateral_gap), sameTopicPairs.map(p => p.bilateral_gap)),
  },
};

// 6) decisions
const decisions = {};
for (const sd of semantic) decisions[sd.decision] = (decisions[sd.decision] ?? 0) + 1;

// 7) best signal — by absolute effect size (Cohen's d)
const effectMap = {
  cosine: Math.abs(separability.cosine.effect_size ?? 0),
  depth: Math.abs(separability.depth.effect_size ?? 0),
  bilateral_gap: Math.abs(separability.bilateral_gap.effect_size ?? 0),
};
const bestSignal = Object.entries(effectMap).sort((a, b) => b[1] - a[1])[0][0];

const result = {
  pairs_total: pairs.length,
  pairs_boundary: boundaryPairs.length,
  pairs_same_topic: sameTopicPairs.length,
  true_word_boundaries: trueWordBoundaries,
  near_words_tolerance: NEAR_WORDS,
  distributions: dist,
  separability,
  decisions,
  best_signal: bestSignal,
  best_signal_effect_sizes: effectMap,
  proposal: {
    best_signal: bestSignal,
    best_signal_effect_size: effectMap[bestSignal],
    config_json_signal: bestSignal, // for completeness
    note: 'T4 emits both depth and bilateral_gap as telemetry. Decision logic UNCHANGED in T4; any tuning would happen in a future T5 based on this calibration.',
  },
};
fs.writeFileSync(here('./calibration-t4.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
