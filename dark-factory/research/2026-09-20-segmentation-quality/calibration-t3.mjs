// T3 calibration analysis over semantic-debug-t3.jsonl + events-t3.jsonl + monolog-meta.json
// Goal: for each sentence with a semantic_debug emission, label as boundary/same-topic
// relative to the 7 true block boundaries, then compare cosine/depth distributions.
// If separability exists, suggest calibrated depthFloor and dispersion multiplier.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const here = p => fileURLToPath(new URL(p, import.meta.url));

const events = fs.readFileSync(here('./events-t3.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
const semantic = fs.readFileSync(here('./semantic-debug-t3.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const meta = JSON.parse(fs.readFileSync(here('./monolog-meta.json'), 'utf8'));

// 1) build sentence_id -> cumulative word offset map from "final" events (ordered by t0)
const finals = events.filter(e => e.type === 'final').sort((a, b) => a.seq - b.seq);
const sentWordEnd = new Map(); // sentence_id -> cumulative word offset AT END
let wOff = 0;
for (const e of finals) {
  const w = (e.sentence.text ?? '').split(/\s+/).filter(Boolean).length;
  wOff += w;
  sentWordEnd.set(e.sentence.id, wOff);
}

// 2) build true block-end word offsets from monolog-meta.json (7 internal boundaries)
const trueWordBoundaries = [];
let acc = 0;
for (const b of meta.blocks) {
  acc += b.words;
  if (b.block < meta.blocks.length) trueWordBoundaries.push(acc);
}

// 3) for each semantic_debug event, look up its sentence's word-end offset
//    boundary = within ±1 sentence (sentence is treated as "near" boundary if
//    its word-end is within ±NEAR_WORDS of any true boundary word offset)
const NEAR_WORDS = 30; // ~1 sentence in this monolog is ~25-40 words
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
    ema_baseline: sd.ema_baseline,
    ema_dispersion: sd.ema_dispersion,
    decision: sd.decision,
  });
}

// 4) distributions
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

const boundaryPairs = pairs.filter(p => p.label === 'boundary');
const sameTopicPairs = pairs.filter(p => p.label === 'same_topic');

const dist = {
  boundary: {
    cosine: stats(boundaryPairs.map(p => p.cosine)),
    depth: stats(boundaryPairs.map(p => p.depth)),
    ema_baseline: stats(boundaryPairs.map(p => p.ema_baseline)),
    ema_dispersion: stats(boundaryPairs.map(p => p.ema_dispersion)),
  },
  same_topic: {
    cosine: stats(sameTopicPairs.map(p => p.cosine)),
    depth: stats(sameTopicPairs.map(p => p.depth)),
    ema_baseline: stats(sameTopicPairs.map(p => p.ema_baseline)),
    ema_dispersion: stats(sameTopicPairs.map(p => p.ema_dispersion)),
  },
};

// 5) decision counts
const decisions = {};
for (const sd of semantic) {
  decisions[sd.decision] = (decisions[sd.decision] ?? 0) + 1;
}

// 6) propose thresholds: depthFloor such that boundary depth < depthFloor <= same_topic depth median (separability heuristic)
//    dispersion multiplier = boundary_dispersion_p25 / same_topic_dispersion_p25 (or 1.0 if not separable)
const prop = (() => {
  const bDepth = dist.boundary.depth;
  const stDepth = dist.same_topic.depth;
  if (!bDepth || !stDepth) return { reason: 'no_data' };
  // separability: boundary depth p25 should be < same_topic depth p25
  const separable = bDepth.p25 < stDepth.p25;
  if (!separable) {
    return {
      separable: false,
      reason: `boundary p25=${bDepth.p25} not less than same_topic p25=${stDepth.p25}`,
      current_default_depth_floor: 'see models/config.json',
      recommended: 'no change',
    };
  }
  const proposedFloor = +(0.5 * (bDepth.p25 + stDepth.p25)).toFixed(4); // midpoint between boundary p25 and same_topic p25
  return {
    separable: true,
    reason: `boundary depth p25=${bDepth.p25} < same_topic p25=${stDepth.p25}`,
    proposed_depth_floor: proposedFloor,
    proposed_dispersion_multiplier: 1.0, // dispersion multiplier not adjusted unless we see clear class difference
    sanity: { boundary_p25_depth: bDepth.p25, same_topic_p25_depth: stDepth.p25 },
  };
})();

const result = {
  pairs_total: pairs.length,
  pairs_boundary: boundaryPairs.length,
  pairs_same_topic: sameTopicPairs.length,
  true_word_boundaries: trueWordBoundaries,
  near_words_tolerance: NEAR_WORDS,
  distributions: dist,
  decisions,
  proposal: prop,
};
fs.writeFileSync(here('./calibration-t3.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
