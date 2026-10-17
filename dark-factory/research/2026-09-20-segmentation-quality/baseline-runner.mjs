// T2 baseline runner: stream monolog.wav in real-time pace through the live pipeline,
// then stop, wait for flush + offline resegmentation (up to 30s), dump ALL events
// via GET /api/sessions/:id/events?from=0 into events-baseline.jsonl. Session NOT deleted.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const base = process.env.BASE_URL ?? 'http://localhost:8088';
const here = p => fileURLToPath(new URL(p, import.meta.url));
const wavPath = process.argv[2] ?? here('./monolog.wav');
const outPath = here('./events-baseline.jsonl');

const wav = fs.readFileSync(wavPath);
if (wav.toString('ascii', 0, 4) !== 'RIFF') throw new Error('not a wav');
let pcm;
for (let i = 12; i + 8 < wav.length;) {
  const id = wav.toString('ascii', i, i + 4), size = wav.readUInt32LE(i + 4);
  if (id === 'data') pcm = wav.subarray(i + 8, i + 8 + size);
  i += 8 + size + (size % 2);
}
if (!pcm) throw new Error('no data chunk');
console.log('audio bytes:', pcm.length, '=', (pcm.length / 2 / 16000).toFixed(1), 's');

const c = await (await fetch(base + '/api/sessions', { method: 'POST' })).json();
console.log('session:', c.id);
const events = [];
const ws = new WebSocket(base.replace('http', 'ws') + '/ws/session');
let ready = false, ack = 0, closed = false;
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', session_id: c.id, token: c.token, from: 0 }));
ws.onmessage = ({ data }) => {
  const e = JSON.parse(data);
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

try {
  await until(() => ready, 30000, 'ready');
  let seq = 0;
  const input = Buffer.concat([pcm, Buffer.alloc(32000)]); // 2s trailing silence, как в smoke
  const started = Date.now();
  for (let offset = 0; offset < input.length; offset += 1024) {
    const packet = Buffer.alloc(1040);
    packet.writeBigUInt64LE(BigInt(++seq));
    packet.writeBigUInt64LE(BigInt(offset / 2), 8);
    input.copy(packet, 16, offset, Math.min(input.length, offset + 1024));
    ws.send(packet);
    await sleep(Math.max(0, started + seq * 32 - Date.now()));
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
  await sleep(500); // добрать хвост событий
} catch (err) {
  console.error('RUNNER ERROR:', err.message);
} finally {
  ws.close();
}

// выгрузка ВСЕХ событий через REST (полная копия, включая всё с from=0)
// сначала надёжно сохраняем события, пойманные через WS
fs.writeFileSync(outPath, events.map(e => JSON.stringify(e)).join('\n') + '\n');
console.log('ws events saved:', events.length);
try {
  const res = await fetch(base + `/api/sessions/${c.id}/events?from=0`, { headers: { Authorization: `Bearer ${c.token}` } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const all = await res.json();
  const list = Array.isArray(all) ? all : (all.events ?? []);
  fs.writeFileSync(outPath, list.map(e => JSON.stringify(e)).join('\n') + '\n');
  console.log('events dumped:', list.length, '->', outPath);
} catch (err) {
  console.error('REST dump failed, keeping ws copy:', err.message);
}
console.log('session kept:', c.id);
