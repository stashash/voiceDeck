import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';

export function isolatedUrl(value, port) {
  const url = new URL(value);
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'Only loopback acceptance services are allowed');
  assert.equal(url.protocol, 'http:');
  assert.equal(url.port, String(port), `Acceptance requires isolated port ${port}`);
  assert.equal(url.pathname, '/');
  assert.ok(!url.username && !url.password && !url.search && !url.hash);
  return url.origin;
}

export function readPcmWav(wav) {
  assert.ok(wav.length >= 44, 'Truncated WAV');
  assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
  assert.equal(wav.toString('ascii', 8, 12), 'WAVE');
  assert.equal(wav.readUInt32LE(4) + 8, wav.length, 'RIFF size mismatch');
  let format, pcm;
  for (let offset = 12; offset < wav.length;) {
    assert.ok(offset + 8 <= wav.length, 'Truncated chunk header');
    const size = wav.readUInt32LE(offset + 4);
    const id = wav.toString('ascii', offset, offset + 4);
    const start = offset + 8;
    assert.ok(start + size <= wav.length, 'Truncated chunk');
    if (id === 'fmt ') {
      assert.ok(!format && size >= 16, 'Invalid format chunk');
      format = {encoding: wav.readUInt16LE(start), channels: wav.readUInt16LE(start + 2),
        rate: wav.readUInt32LE(start + 4), byteRate: wav.readUInt32LE(start + 8),
        blockAlign: wav.readUInt16LE(start + 12), bits: wav.readUInt16LE(start + 14)};
    }
    if (id === 'data') { assert.ok(!pcm, 'Multiple PCM chunks'); pcm = wav.subarray(start, start + size); }
    offset = start + size + size % 2;
  }
  assert.deepEqual(format, {encoding: 1, channels: 1, rate: 16000, byteRate: 32000, blockAlign: 2, bits: 16});
  assert.ok(pcm?.length && pcm.length % 2 === 0, 'Empty or unaligned PCM');
  assert.ok(pcm.length <= 32000 * 45, 'Fixture exceeds 45 seconds; audio is never silently truncated');
  assert.ok(pcm.some(byte => byte !== 0), 'Silent fixture');
  return pcm;
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function json(url, init) {
  const response = await fetch(url, {...init, signal: AbortSignal.timeout(10000)});
  assert.ok(response.ok, `${init?.method ?? 'GET'} ${url}: HTTP ${response.status}`);
  return response.json();
}

/** Sends real PCM, never text frames. This bypasses microphone capture and room acoustics. */
export async function replayAudio(file, {base = 'http://127.0.0.1:8089', timeoutMs = 60000, trailingSilenceMs = 1000} = {}) {
  base = isolatedUrl(base, 8089);
  assert.ok(Number.isInteger(trailingSilenceMs) && trailingSilenceMs >= 0 && trailingSilenceMs <= 2000);
  const wav = await fs.readFile(file), pcm = readPcmWav(wav);
  const health = await json(`${base}/health`);
  assert.equal(health.mode, 'live', 'Demo transcripts are not ASR acceptance');
  assert.equal(health.asr, 'sherpa-onnx');
  const session = await json(`${base}/api/sessions`, {method: 'POST'});
  assert.equal(session.mode, 'live');
  const events = [], origin = performance.now();
  let ws, failure, ready = false, ack = 0, lastUtteranceAt = 0, lastAckAt = 0, firstUtteranceAt;
  let started, stoppedAt, packetCount = 0, cleanup;
  async function until(check) {
    while (!check()) {
      if (failure) throw failure;
      assert.ok(performance.now() - origin < timeoutMs, 'Local ASR replay timed out');
      await sleep(20);
    }
  }
  try {
    ws = new WebSocket(`${base.replace('http:', 'ws:')}/ws/session`);
    ws.onopen = () => ws.send(JSON.stringify({type: 'auth', session_id: session.id, token: session.token, from: 0}));
    ws.onerror = () => { failure = Error('ASR WebSocket error'); };
    ws.onclose = event => { failure ??= Error(`ASR WebSocket closed ${event.code}`); };
    ws.onmessage = ({data}) => {
      try {
        const event = JSON.parse(data); events.push({...event, receivedMs: performance.now() - origin});
        if (event.type === 'ready') ready = true;
        if (event.type === 'audio_ack') { ack = event.audio_seq; lastAckAt = performance.now(); }
        if (event.type === 'editor_utterance' && event.text?.trim()) {
          lastUtteranceAt = performance.now(); firstUtteranceAt ??= lastUtteranceAt;
        }
        if (['warning', 'audio_resync', 'chunk', 'slide', 'error'].includes(event.type)) {
          failure = Error(`Unexpected editor audio event: ${JSON.stringify(event)}`);
        }
      } catch (error) { failure = error; }
    };
    await until(() => ready);
    ws.send(JSON.stringify({type: 'editor_mode'}));
    const input = Buffer.concat([pcm, Buffer.alloc(trailingSilenceMs * 32)]);
    started = performance.now();
    for (let offset = 0; offset < input.length; offset += 1024) {
      if (failure) throw failure;
      const packet = Buffer.alloc(1040);
      packet.writeBigUInt64LE(BigInt(++packetCount));
      packet.writeBigUInt64LE(BigInt(offset / 2), 8);
      input.copy(packet, 16, offset, Math.min(input.length, offset + 1024));
      ws.send(packet);
      await sleep(Math.max(0, started + packetCount * 32 - performance.now()));
    }
    await until(() => ack === packetCount);
    stoppedAt = performance.now();
    ws.send(JSON.stringify({type: 'stop'}));
    await until(() => events.some(e => e.type === 'flushed'));
    if (failure) throw failure;
    const utterances = events.filter(e => e.type === 'editor_utterance').map(e => e.text);
    assert.ok(utterances.length, 'ASR completed without a recognized utterance');
    return {
      mode: 'synthetic-pcm-replay', microphoneCaptureTested: false, file,
      sha256: createHash('sha256').update(wav).digest('hex'), sampleRate: 16000,
      sourceAudioMs: pcm.length / 32, paddedAudioMs: packetCount * 32, trailingSilenceMs,
      packetsSent: packetCount, packetsAcknowledged: ack, utterances,
      timing: {firstUtteranceFromReplayMs: firstUtteranceAt - started,
        lastUtteranceFromReplayMs: lastUtteranceAt - started,
        allAcksFromReplayMs: lastAckAt - started, stopToLastUtteranceMs: Math.max(0, lastUtteranceAt - stoppedAt),
        totalMs: performance.now() - origin},
      warnings: events.filter(e => e.type === 'warning'),
      generationEvents: events.filter(e => ['chunk', 'slide'].includes(e.type)), events,
    };
  } catch (error) {
    error.replayEvidence = {file, packetsSent: packetCount, packetsAcknowledged: ack, events};
    throw error;
  } finally {
    if (ws) { ws.onclose = null; ws.close(); }
    cleanup = await fetch(`${base}/api/sessions/${encodeURIComponent(session.id)}/data`, {
      method: 'DELETE', headers: {Authorization: `Bearer ${session.token}`}, signal: AbortSignal.timeout(10000),
    });
    assert.ok(cleanup.ok, `Isolated ASR session cleanup failed: ${cleanup.status}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    assert.ok(process.argv[2], 'Usage: node scripts/voice-factory-audio.mjs fixture.wav');
    console.log(JSON.stringify(await replayAudio(process.argv[2], {base: process.env.VOICE_FACTORY_AUDIO_URL}), null, 2));
  } catch (error) {
    console.error(JSON.stringify({result: 'FAIL', error: String(error), replay: error.replayEvidence}));
    process.exitCode = 1;
  }
}
