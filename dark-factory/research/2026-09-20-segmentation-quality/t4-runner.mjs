// T4 retest runner — adapted from t3-runner.mjs.
// Same pacing/save strategy as T3 (1ms/packet, periodic .partial.jsonl writes).
// Differs from T3 runner only in output filenames:
//   events-t3.jsonl           -> events-t4.jsonl
//   events-t3.partial.jsonl   -> events-t4.partial.jsonl
//   semantic-debug-t3.jsonl   -> semantic-debug-t4.jsonl
//   semantic-debug-t3.partial.jsonl -> semantic-debug-t4.partial.jsonl
// semantic_debug wire event now carries an additional 'bilateral_gap' field
// (see t4-semantic-debug-protocol.md). The schema change is handled by the
// server; this runner treats semantic_debug as opaque JSONL.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const base = process.env.BASE_URL ?? 'http://localhost:8088';
const here = p => fileURLToPath(new URL(p, import.meta.url));
const wavPath = process.argv[2] ?? here('./monolog.wav');
const eventsPath = here('./events-t4.jsonl');
const semanticPath = here('./semantic-debug-t4.jsonl');
const eventsPartialPath = here('./events-t4.partial.jsonl');
const semanticPartialPath = here('./semantic-debug-t4.partial.jsonl');

// ms per packet. T3 baseline used 32 (real-time 16kHz mono). T3 v2 used 1ms
// (~32x faster). T4 retest keeps 1ms pacing for retest parity with T3.
const PACKET_INTERVAL_MS = Number(process.env.PACKET_INTERVAL_MS ?? 1);

const wav = fs.readFileSync(wavPath);
if (wav.toString('ascii', 0, 4) !== 'RIFF') throw new Error('not a wav');
let pcm;
for (let i = 12; i + 8 < wav.length;) {
  const id = wav.toString('ascii', i, i + 4), size = wav.readUInt32LE(i + 4);
  if (id === 'data') pcm = wav.subarray(i + 8, i + 8 + size);
  i += 8 + size + (size % 2);
}
if (!pcm) throw new Error('no data chunk');
console.log('audio bytes:', pcm.length, '=', (pcm.length / 2 / 16000).toFixed(1), 's', 'packet interval ms:', PACKET_INTERVAL_MS);

const c = await (await fetch(base + '/api/sessions', { method: 'POST' })).json();
console.log('session:', c.id);
const events = [];
const semanticEvents = [];
const ws = new WebSocket(base.replace('http', 'ws') + '/ws/session');
let ready = false, ack = 0, closed = false;
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', session_id: c.id, token: c.token, from: 0 }));
ws.onmessage = ({ data }) => {
  let e;
  try { e = JSON.parse(data); } catch { return; }
  if (e && e.type === 'semantic_debug') {
    semanticEvents.push(e);
    return;
  }
  events.push(e);
  if (e.type === 'ready') ready = true;
  if (e.type === 'audio_ack') ack = e.audio_seq;
  if (e.type === 'flushed') console.log('FLUSHED at', new Date().toISOString());
  if (e.type === 'chunk') console.log('CHUNK', e.reason, 'words:', (e.chunk.text || '').split(/\s+/).length, 'status:', e.chunk.status);
  if (e.type === 'chunk_revise') console.log('REVISE', e.operation, e.source, 'chunks:', e.chunks.length);
  if (e.type === 'warning') console.error('WARNING', e.message);
};
ws.onclose = () => { closed = true; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(check, timeout, label) {
  const start = Date.now();
  while (!check()) {
    if (Date.now() - start > timeout) throw new Error('timeout: ' + label);
    await sleep(50);
  }
}

// periodic saver: write current buffers to .partial.jsonl files every 5s
let lastPartialWrite = 0;
function maybeWritePartial(force = false) {
  const now = Date.now();
  if (!force && now - lastPartialWrite < 5000) return;
  lastPartialWrite = now;
  try {
    fs.writeFileSync(eventsPartialPath, events.map(e => JSON.stringify(e)).join('\n') + (events.length ? '\n' : ''));
    fs.writeFileSync(semanticPartialPath, semanticEvents.map(e => JSON.stringify(e)).join('\n') + (semanticEvents.length ? '\n' : ''));
  } catch (err) {
    console.error('partial write failed:', err.message);
  }
}
setInterval(() => maybeWritePartial(false), 1000);

try {
  await until(() => ready, 30000, 'ready');
  let seq = 0;
  const input = Buffer.concat([pcm, Buffer.alloc(32000)]); // 2s trailing silence
  const started = Date.now();
  for (let offset = 0; offset < input.length; offset += 1024) {
    const packet = Buffer.alloc(1040);
    packet.writeBigUInt64LE(BigInt(++seq));
    packet.writeBigUInt64LE(BigInt(offset / 2), 8);
    input.copy(packet, 16, offset, Math.min(input.length, offset + 1024));
    ws.send(packet);
    if (PACKET_INTERVAL_MS > 0) {
      await sleep(Math.max(0, started + seq * PACKET_INTERVAL_MS - Date.now()));
    }
    if (seq % 1000 === 0) {
      const elapsed = ((Date.now() - started) / 1000).toFixed(1);
      const total = (input.length / 1024).toFixed(0);
      console.log(`stream ${seq}/${total} (${elapsed}s) events=${events.length} semantic=${semanticEvents.length}`);
    }
  }
  console.log('stream done,', seq, 'packets in', ((Date.now() - started) / 1000).toFixed(1) + 's');
  await until(() => ack === seq, 60000, 'all acked');
  ws.send(JSON.stringify({ type: 'stop' }));
  await until(() => events.some(e => e.type === 'flushed'), 60000, 'flushed');
  // ждём offline-проход (chunk_revise operation=offline) до 30 с
  const t0 = Date.now();
  while (Date.now() - t0 < 30000) {
    if (events.some(e => e.type === 'chunk_revise' && e.operation === 'offline')) break;
    await sleep(250);
  }
  console.log('offline revise seen:', events.some(e => e.type === 'chunk_revise' && e.operation === 'offline'));
  console.log('semantic_debug events seen (ws):', semanticEvents.length);
  await sleep(500); // добрать хвост событий
  maybeWritePartial(true);
} catch (err) {
  console.error('RUNNER ERROR:', err.message);
  maybeWritePartial(true);
} finally {
  ws.close();
}

// (a) final write of semantic-debug events FIRST
fs.writeFileSync(semanticPath, semanticEvents.map(e => JSON.stringify(e)).join('\n') + (semanticEvents.length ? '\n' : ''));
console.log('semantic events saved:', semanticEvents.length, '->', semanticPath);

// (b) REST dump of all main events
fs.writeFileSync(eventsPath, events.map(e => JSON.stringify(e)).join('\n') + '\n');
console.log('ws events saved:', events.length);
try {
  const res = await fetch(base + `/api/sessions/${c.id}/events?from=0`, { headers: { Authorization: `Bearer ${c.token}` } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const all = await res.json();
  const list = Array.isArray(all) ? all : (all.events ?? []);
  fs.writeFileSync(eventsPath, list.map(e => JSON.stringify(e)).join('\n') + '\n');
  console.log('events dumped:', list.length, '->', eventsPath);
} catch (err) {
  console.error('REST dump failed, keeping ws copy:', err.message);
}

console.log('session id:', c.id);

// (c) THEN delete the session
try {
  const del = await fetch(base + `/api/sessions/${c.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${c.token}` } });
  console.log('session deleted:', del.status);
} catch (err) {
  console.error('session delete failed:', err.message);
}
