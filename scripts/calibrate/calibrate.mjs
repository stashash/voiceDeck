#!/usr/bin/env node
// VoiceDeck segmentation calibration.
// Usage: node scripts/calibrate/calibrate.mjs corpus/<name> [corpus/<name2> ...]
// Reads transcript.tsv + boundaries.tsv, runs bge-m3 embeddings via Ollama,
// simulates the live depth-score algorithm, and reports Pk / WindowDiff / F1(±1).
import fs from 'node:fs';
import path from 'node:path';

const OLLAMA = process.env.EMBEDDING_URL ?? 'http://127.0.0.1:11434/v1';
const MODEL = process.env.EMBEDDING_MODEL ?? 'bge-m3-embed';
const BLOCK = 3;           // sentences per embedding block (matches Models.joinBlock)
const EMA_ALPHA = 0.1;     // matches Session.semantic
const MIN_WORDS = 60;      // chunkSizeMin

function cosine(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i]; }
  return na === 0 || nb === 0 ? 1 : dot / Math.sqrt(na*nb);
}

async function embed(text) {
  const res = await fetch(OLLAMA + '/embeddings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: MODEL, input: [text] })
  });
  if (!res.ok) throw new Error('Ollama HTTP ' + res.status);
  const data = await res.json();
  const v = data.data[0].embedding;
  const n = Math.sqrt(v.reduce((s, x) => s + x*x, 0));
  return v.map(x => x / (n || 1));
}

function loadCorpus(dir) {
  const tFile = path.join(dir, 'transcript.tsv');
  const bFile = path.join(dir, 'boundaries.tsv');
  if (!fs.existsSync(tFile) || !fs.existsSync(bFile)) throw new Error('Missing transcript.tsv/boundaries.tsv in ' + dir);
  const sentences = fs.readFileSync(tFile, 'utf8').split(/\r?\n/).filter(l => l.trim()).map(l => l.split('\t')[1] ?? l);
  const labels = new Set(fs.readFileSync(bFile, 'utf8').split(/\r?\n/).filter(l => l.trim()).map(l => parseInt(l.split('\t')[0], 10)));
  for (const b of labels) if (!Number.isInteger(b) || b < 1 || b >= sentences.length) throw new Error('Invalid boundary index ' + b + ' in ' + dir);
  return { sentences, labels };
}

// Live algorithm mirror: block embeddings + EMA depth-score + emergency floor.
function predictBoundaries(vectors, sentences, { dispersionK = 1.6, floorDepth = 0.12, sanityCos = 0.55, emergency = 0.2 } = {}) {
  const predicted = new Set();
  let baseline = 0, dispersion = 0, count = 0;
  let pendingWords = 0;
  for (let i = 1; i < vectors.length; i++) {
    const cos = cosine(vectors[i-1], vectors[i]);
    if (count === 0) { baseline = cos; dispersion = 0.05; count = 1; }
    else { const dev = Math.abs(cos - baseline); baseline += EMA_ALPHA * (cos - baseline); dispersion += EMA_ALPHA * (dev - dispersion); count++; }
    const depth = baseline - cos;
    pendingWords = sentences.slice(Math.max(0, i - 8), i).join(' ').split(/\s+/).length; // rough pending estimate
    const emergencyHit = cos < emergency;
    const deepDip = count >= 5 && depth > Math.max(floorDepth, dispersionK * dispersion) && cos < sanityCos;
    if (pendingWords >= 20 && (emergencyHit || deepDip)) predicted.add(i); // approximate: real system requires 60 words since last boundary
  }
  return predicted;
}

// Pk / WindowDiff: probability that two sentences k apart are inconsistently classified.
function pk(ref, hyp, n, k = null) {
  k = k ?? Math.max(2, Math.floor(n / (2 * Math.max(1, ref.size + 1))));
  let errors = 0, total = 0;
  for (let i = 0; i + k < n; i++) {
    const r = hasBoundaryBetween(ref, i, i + k), h = hasBoundaryBetween(hyp, i, i + k);
    if (r !== h) errors++;
    total++;
  }
  return total === 0 ? 0 : errors / total;
}
function hasBoundaryBetween(set, i, j) { for (let x = i + 1; x <= j; x++) if (set.has(x)) return true; return false; }
function windowDiff(ref, hyp, n, k = null) {
  k = k ?? Math.max(2, Math.floor(n / (2 * Math.max(1, ref.size + 1))));
  let errors = 0, total = 0;
  for (let i = 0; i + k < n; i++) {
    const r = countBetween(ref, i, i + k), h = countBetween(hyp, i, i + k);
    if (r !== h) errors++;
    total++;
  }
  return total === 0 ? 0 : errors / total;
}
function countBetween(set, i, j) { let c = 0; for (let x = i + 1; x <= j; x++) if (set.has(x)) c++; return c; }
function f1(ref, hyp, tolerance = 1) {
  let tp = 0;
  for (const h of hyp) { for (let d = -tolerance; d <= tolerance; d++) if (ref.has(h + d)) { tp++; break; } }
  const prec = hyp.size === 0 ? 0 : tp / hyp.size;
  const rec = ref.size === 0 ? 0 : tp / ref.size;
  return prec + rec === 0 ? 0 : 2 * prec * rec / (prec + rec);
}

const dirs = process.argv.slice(2);
if (dirs.length === 0) { console.error('Usage: node calibrate.mjs corpus/<name> [...]'); process.exit(1); }

let allPk = [], allWd = [], allF1 = [];
for (const dir of dirs) {
  const { sentences, labels } = loadCorpus(dir);
  console.log('== ' + dir + ' == ' + sentences.length + ' sentences, ' + labels.size + ' labeled boundaries');
  const vectors = [];
  for (let i = 0; i < sentences.length; i++) {
    const block = sentences.slice(Math.max(0, i - BLOCK + 1), i + 1).join(' ');
    vectors.push(await embed(block));
    if (i % 20 === 0) process.stderr.write('  embed ' + i + '/' + sentences.length + '\r');
  }
  const hyp = predictBoundaries(vectors, sentences);
  const n = sentences.length;
  const P = pk(labels, hyp, n), W = windowDiff(labels, hyp, n), F = f1(labels, hyp);
  allPk.push(P); allWd.push(W); allF1.push(F);
  console.log('  predicted: ' + [...hyp].sort((a,b)=>a-b).join(', ') || '(none)');
  console.log('  labeled:   ' + [...labels].sort((a,b)=>a-b).join(', ') || '(none)');
  console.log('  Pk=' + P.toFixed(3) + '  WindowDiff=' + W.toFixed(3) + '  F1(±1)=' + F.toFixed(3));
}
if (dirs.length > 1) {
  const avg = a => a.reduce((s, x) => s + x, 0) / a.length;
  console.log('== AVERAGE == Pk=' + avg(allPk).toFixed(3) + '  WindowDiff=' + avg(allWd).toFixed(3) + '  F1=' + avg(allF1).toFixed(3));
}
console.log('Target: F1 >= 0.7. If below: adjust dispersionK / sanityCos / emergency and rerun.');
