import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {registerHooks} from 'node:module';
import {isDeepStrictEqual} from 'node:util';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {readPcmWav, replayAudio} from './voice-factory-audio.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const stage = new URL('../frontend/src/stage/', import.meta.url).href;
const parserFiles = ['deckVoice.ts', 'deckVoiceExtended.ts', 'textVoice.ts', 'voiceVocabulary.ts'];
const transportOrigin = 'http://127.0.0.1:8089';
const sha256 = value => createHash('sha256').update(value).digest('hex');
export const historicalBaseline = Object.freeze({passed: 5, total: 9, source_kind: 'synthetic',
  corpus: 'eSpeak NG ru135', source: 'scripts/voice-factory-verdict.md', newly_measured: false});

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

export function corpusHash(manifest) {
  const {corpus_sha256, ...content} = manifest;
  return sha256(canonicalJson(content));
}

export function parseManifestJson(source) {
  const result = JSON.parse(source);
  // JSON.parse accepts duplicate keys; reject ambiguous labels before validating the parsed object.
  const tokens = source.match(/"(?:\\[\s\S]|[^"\\])*"|[{}\[\]:,]/g) ?? [];
  const stack = [];
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (token === '{') stack.push(new Set());
    else if (token === '[') stack.push(null);
    else if (token === '}' || token === ']') stack.pop();
    else if (token.startsWith('"') && tokens[i + 1] === ':') {
      const key = JSON.parse(token), keys = stack.at(-1);
      assert.ok(keys && !keys.has(key), `Duplicate JSON key: ${key}`);
      keys.add(key);
    }
  }
  return result;
}

function object(value, keys, label) {
  assert.ok(value && typeof value === 'object' && !Array.isArray(value), `${label}: expected object`);
  assert.deepEqual(Object.keys(value).sort(), [...keys].sort(), `${label}: missing or unknown fields`);
}

function text(value, label, max = 12000) {
  assert.ok(typeof value === 'string' && value.trim().length > 0 && value.length <= max, `${label}: expected nonempty string`);
}

function id(value, label) {
  assert.ok(typeof value === 'string' && /^[a-z0-9][a-z0-9_-]{0,79}$/.test(value), `${label}: invalid identifier`);
}

function hash(value, label) {
  assert.ok(typeof value === 'string' && /^[a-f0-9]{64}$/.test(value), `${label}: expected lowercase SHA256`);
}

function jsonValue(value, label, depth = 0) {
  assert.ok(depth < 12, `${label}: nested too deeply`);
  if (typeof value === 'number') assert.ok(Number.isFinite(value), `${label}: non-finite number`);
  else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      assert.ok(!['__proto__', 'constructor', 'prototype'].includes(key), `${label}: unsafe key`);
      jsonValue(child, label, depth + 1);
    }
  } else assert.ok(value === null || ['string', 'boolean'].includes(typeof value), `${label}: invalid JSON value`);
}

export function validateManifest(manifest) {
  object(manifest, ['schema_version', 'corpus_id', 'corpus_sha256', 'speakers', 'cases'], 'manifest');
  assert.equal(manifest.schema_version, 1, 'Unsupported manifest version');
  id(manifest.corpus_id, 'corpus_id'); hash(manifest.corpus_sha256, 'corpus_sha256');
  assert.ok(Array.isArray(manifest.speakers) && manifest.speakers.length > 0 && manifest.speakers.length <= 1000, 'Invalid speakers');
  const speakers = new Map();
  for (const speaker of manifest.speakers) {
    object(speaker, ['id', 'kind', 'split', 'provenance', 'consent'], 'speaker');
    id(speaker.id, 'speaker.id');
    assert.ok(!speakers.has(speaker.id), 'Duplicate speaker; one speaker cannot cross splits');
    assert.ok(['human', 'synthetic'].includes(speaker.kind), 'Unknown speaker kind');
    assert.ok(['development', 'holdout'].includes(speaker.split), 'Unknown speaker split');
    text(speaker.provenance, 'speaker.provenance', 2000);
    assert.equal(speaker.consent, speaker.kind === 'human' ? 'recording-consented' : 'not-applicable', 'Human recordings require consent');
    speakers.set(speaker.id, speaker);
  }
  assert.ok(Array.isArray(manifest.cases) && manifest.cases.length > 0 && manifest.cases.length <= 2000, 'Invalid cases');
  const ids = new Set(), hashes = new Set(), paths = new Set(), usedSpeakers = new Set();
  for (const item of manifest.cases) {
    object(item, ['id', 'speaker_id', 'condition', 'wav', 'sha256', 'expected'], 'case');
    id(item.id, 'case.id');
    assert.ok(!ids.has(item.id), 'Duplicate case id'); ids.add(item.id);
    assert.ok(speakers.has(item.speaker_id), 'Unknown speaker_id'); usedSpeakers.add(item.speaker_id);
    text(item.condition, 'condition', 2000); text(item.wav, 'wav', 500); hash(item.sha256, 'wav.sha256');
    assert.ok(/\.wav$/i.test(item.wav) && !/[\\:\x00-\x1f]/.test(item.wav) && !path.posix.isAbsolute(item.wav)
      && item.wav.split('/').every(part => part && part !== '.' && part !== '..'), 'WAV must be a relative contained path');
    assert.ok(!paths.has(item.wav.toLowerCase()), 'Duplicate WAV path'); paths.add(item.wav.toLowerCase());
    assert.ok(!hashes.has(item.sha256), 'Duplicate audio hash; recordings cannot leak across splits'); hashes.add(item.sha256);
    const expected = item.expected;
    object(expected, ['transcript', 'action', 'target', 'arguments'], 'expected');
    text(expected.transcript, 'expected.transcript'); text(expected.action, 'expected.action', 80);
    object(expected.target, ['slide', 'element'], 'expected.target');
    for (const value of Object.values(expected.target)) assert.ok(value === null || (Number.isSafeInteger(value) && value >= 0), 'Target must be null or a nonnegative integer');
    assert.ok(expected.arguments && typeof expected.arguments === 'object' && !Array.isArray(expected.arguments), 'arguments must be an object');
    jsonValue(expected.arguments, 'arguments');
  }
  assert.equal(usedSpeakers.size, speakers.size, 'Unused speaker entry');
  assert.equal(corpusHash(manifest), manifest.corpus_sha256, 'Corpus hash mismatch (metadata or labels changed)');
  return manifest;
}

// The production parser has only local, erasable TypeScript imports. No executor is loaded.
export async function loadProductionParser() {
  const hook = registerHooks({resolve(specifier, context, next) {
    if (context.parentURL?.startsWith(stage) && specifier.startsWith('./') && !path.extname(specifier)) {
      assert.ok(parserFiles.includes(`${specifier.slice(2)}.ts`), 'Review new parser dependency before accepting it');
      specifier += '.ts';
    }
    return next(specifier, context);
  }});
  try { return (await import(`${stage}deckVoice.ts`)).parseDeckVoice; }
  finally { hook.deregister(); }
}

export function actionSlots(parsed) {
  const {kind, slide, elementNumber, ...args} = parsed;
  const target = {slide: slide ?? null, element: elementNumber ?? null};
  if (kind === 'element') { target.element = args.number; delete args.number; }
  if (kind === 'select') { target.slide = args.number; delete args.number; }
  return {action: kind, target, arguments: JSON.parse(JSON.stringify(args))};
}

export async function loadCorpus(manifestFile, audioRoot, parse = undefined) {
  const bytes = await fs.readFile(manifestFile);
  assert.ok(bytes.length <= 8 * 1024 * 1024, 'Manifest exceeds 8 MiB');
  const manifest = validateManifest(parseManifestJson(new TextDecoder('utf-8', {fatal: true}).decode(bytes)));
  parse ??= await loadProductionParser();
  const directory = await fs.realpath(audioRoot ?? path.dirname(path.resolve(manifestFile)));
  const files = new Map(); let totalBytes = 0;
  for (const item of manifest.cases) {
    const real = await fs.realpath(path.resolve(directory, item.wav));
    const relative = path.relative(directory, real);
    assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'WAV symlink escapes audio root');
    const stat = await fs.stat(real);
    assert.ok(stat.isFile() && stat.size <= 2 * 1024 * 1024, 'WAV is not a bounded regular file');
    totalBytes += stat.size;
    assert.ok(totalBytes <= 256 * 1024 * 1024, 'Corpus exceeds 256 MiB; use a separate manifest');
    const wav = await fs.readFile(real);
    assert.equal(sha256(wav), item.sha256, `${item.id}: WAV hash mismatch`);
    readPcmWav(wav);
    const {transcript, ...expected} = item.expected;
    assert.deepEqual(actionSlots(parse(transcript)), expected, `${item.id}: gold labels disagree with parser contract`);
    files.set(item.id, wav);
  }
  return {manifest, files, manifest_sha256: sha256(bytes), parse};
}

export function normalizeTranscript(value) {
  return value.normalize('NFC').toLowerCase().replace(/ё/g, 'е')
    .replace(/(?<![\p{L}\p{N}_])двадцать четыре(?![\p{L}\p{N}_])/gu, '24')
    .replace(/(?<![\p{L}\p{N}_])двадцать(?![\p{L}\p{N}_])/gu, '20')
    .replace(/(?<![\p{L}\p{N}_])один(?![\p{L}\p{N}_])/gu, '1')
    .replace(/(?<!\d)[.,!?;:]|[.,!?;:](?!\d)/gu, ' ').replace(/\s+/g, ' ').trim();
}

export function scoreCase(item, utterances, parse) {
  assert.ok(Array.isArray(utterances) && utterances.every(value => typeof value === 'string'), 'Invalid ASR utterances');
  const start = performance.now();
  const actual = utterances.length === 1 ? actionSlots(parse(utterances[0])) : null;
  const parserMs = utterances.length === 1 ? performance.now() - start : null;
  const transcript_match = utterances.length === 1 && normalizeTranscript(utterances[0]) === normalizeTranscript(item.expected.transcript);
  const slots = {
    action: actual?.action === item.expected.action,
    target: isDeepStrictEqual(actual?.target, item.expected.target),
    arguments: isDeepStrictEqual(actual?.arguments, item.expected.arguments),
  };
  return {utterances, actual, transcript_match, slots, complete_command: transcript_match && Object.values(slots).every(Boolean), parser_ms: parserMs};
}

function metrics(cases) {
  return {cases: cases.length, complete_commands: cases.filter(c => c.complete_command).length,
    complete_command_errors: cases.filter(c => !c.complete_command).length,
    complete_command_rate: cases.length ? cases.filter(c => c.complete_command).length / cases.length : null,
    transcript_errors: cases.filter(c => !c.transcript_match).length,
    slot_errors: Object.fromEntries(['action', 'target', 'arguments'].map(key => [key, cases.filter(c => !c.slots[key]).length])),
    replay_errors: cases.filter(c => c.error).length};
}

export function summarize(cases) {
  const groups = keys => [...new Set(cases.map(c => keys.map(key => c[key]).join('/')))].map(key => {
    const members = cases.filter(c => keys.map(field => c[field]).join('/') === key);
    return {group: key, ...metrics(members)};
  });
  return {total_cases: cases.length, failed_cases: cases.filter(c => !c.complete_command).length,
    by_kind_and_split: groups(['source_kind', 'split']), by_speaker: groups(['source_kind', 'split', 'speaker_id'])};
}

export function localEndpoint(value) {
  const url = new URL(value);
  assert.equal(url.protocol, 'http:', 'Only local HTTP endpoints are supported');
  assert.ok(['127.0.0.1', '[::1]'].includes(url.hostname), 'Use a loopback IP literal, without DNS');
  assert.ok(Number(url.port) >= 1024 && !['8088', '8090', '5174'].includes(url.port), 'Use an isolated port, never production/preview ports');
  assert.ok(url.pathname === '/' && !url.username && !url.password && !url.search && !url.hash, 'Expected a bare local origin');
  return url.origin;
}

export function localFetch(base, fetchImpl) {
  base = localEndpoint(base);
  return (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    assert.equal(url.origin, transportOrigin, 'Unexpected transport origin');
    assert.ok(!url.username && !url.password && !url.search && !url.hash, 'Invalid ASR URL');
    assert.ok(['/health', '/api/sessions'].includes(url.pathname) || /^\/api\/sessions\/[^/]+\/data$/.test(url.pathname), 'Unexpected ASR path');
    return fetchImpl(`${base}${url.pathname}`, {...init, redirect: 'error'});
  };
}

export function localWebSocket(base, WebSocketImpl) {
  base = localEndpoint(base);
  return class extends WebSocketImpl {
    constructor(value, protocols) {
      assert.equal(String(value), `${transportOrigin.replace('http:', 'ws:')}/ws/session`, 'Unexpected WebSocket destination');
      super(`${base.replace('http:', 'ws:')}/ws/session`, protocols);
    }
  };
}

async function sourceHashes() {
  const files = ['scripts/voice-asr-evaluate.mjs', 'scripts/voice-factory-audio.mjs', ...parserFiles.map(file => `frontend/src/stage/${file}`)];
  return Object.fromEntries(await Promise.all(files.map(async file => [file, sha256(await fs.readFile(path.join(root, file)))])));
}

export async function evaluate(corpus, options, replay = replayAudio) {
  const base = localEndpoint(options.base ?? 'http://127.0.0.1:8089');
  const trailingSilenceMs = options.trailingSilenceMs ?? 1000;
  assert.ok(Number.isInteger(trailingSilenceMs) && trailingSilenceMs >= 0 && trailingSilenceMs <= 2000, 'Invalid trailing silence');
  text(options.runLabel, 'run label', 200);
  text(options.runtimeLabel, 'runtime label', 2000);
  const report = {schema_version: 1, result: 'FAIL', scope: 'local-pcm-asr-and-production-parser-only',
    historical_baseline: historicalBaseline, corpus_id: corpus.manifest.corpus_id,
    corpus_sha256: corpus.manifest.corpus_sha256, manifest_sha256: corpus.manifest_sha256,
    source_sha256: await sourceHashes(), node_version: process.version,
    run_label: options.runLabel, runtime_label: options.runtimeLabel, runtime_identity: 'operator-declared, not attested',
    endpoint: base, trailing_silence_ms: trailingSilenceMs, started_at: new Date().toISOString(),
    not_measured: ['physical_microphone', 'asr_compute_ms', 'speech_end_to_visible_ms', 'queue_ms', 'execution_ms', 'persistence_ms', 'export_ms'],
    cases: []};
  // Replay verified private snapshots, so a source WAV changing after validation cannot be sent.
  const temporaryRoot = path.join(root, '.voice-factory');
  await fs.mkdir(temporaryRoot, {recursive: true});
  const temporaryRelative = path.relative(await fs.realpath(root), await fs.realpath(temporaryRoot));
  assert.ok(temporaryRelative && !temporaryRelative.startsWith('..') && !path.isAbsolute(temporaryRelative), 'Snapshot directory escapes worktree');
  const snapshot = await fs.mkdtemp(path.join(temporaryRoot, 'asr-eval-'));
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  // The existing transport pins 8089. Remap only its known origin, preserving its PCM/framing/flush logic.
  globalThis.fetch = localFetch(base, originalFetch);
  globalThis.WebSocket = localWebSocket(base, originalWebSocket);
  try {
    for (const item of corpus.manifest.cases) {
      const speaker = corpus.manifest.speakers.find(s => s.id === item.speaker_id);
      const record = {id: item.id, speaker_id: speaker.id, source_kind: speaker.kind, split: speaker.split,
        condition: item.condition, sha256: item.sha256, expected: item.expected};
      report.cases.push(record);
      const start = performance.now();
      try {
        const file = path.join(snapshot, `${item.id}.wav`);
        const wav = corpus.files.get(item.id);
        assert.equal(sha256(wav), item.sha256, 'Validated buffer changed');
        await fs.writeFile(file, wav, {flag: 'wx'});
        const evidence = await replay(file, {base: transportOrigin, trailingSilenceMs});
        const {mode, file: snapshotFile, ...actualEvidence} = evidence;
        record.replay = actualEvidence;
        assert.equal(evidence.sha256, item.sha256, 'Replayed WAV hash mismatch');
        assert.ok(evidence.packetsSent > 0 && evidence.packetsSent === evidence.packetsAcknowledged, 'Unacknowledged PCM');
        assert.ok(Array.isArray(evidence.events) && evidence.events.some(e => e.type === 'flushed'), 'Missing ASR flush');
        assert.ok(!evidence.events.some(e => ['warning', 'audio_resync', 'chunk', 'slide', 'error'].includes(e.type)), 'Unexpected ASR event');
        Object.assign(record, scoreCase(item, evidence.utterances, corpus.parse));
      } catch (error) {
        Object.assign(record, {error: String(error), utterances: [], actual: null, transcript_match: false,
          slots: {action: false, target: false, arguments: false}, complete_command: false, parser_ms: null});
        if (error.replayEvidence) record.replay_failure = error.replayEvidence;
      }
      record.replay_and_scoring_wall_ms = performance.now() - start;
    }
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
    const snapshotRelative = path.relative(await fs.realpath(temporaryRoot), await fs.realpath(snapshot));
    assert.ok(snapshotRelative && !snapshotRelative.startsWith('..') && !path.isAbsolute(snapshotRelative), 'Refusing cleanup outside snapshot directory');
    await fs.rm(snapshot, {recursive: true, force: true});
  }
  report.completed_at = new Date().toISOString();
  report.summary = summarize(report.cases);
  report.result = report.summary.failed_cases === 0 ? 'PASS' : 'FAIL';
  return report;
}

const help = `Local ASR evaluation (Node >=22.18). Historical synthetic baseline: 5/9, not human accuracy.
Usage: node scripts/voice-asr-evaluate.mjs --manifest FILE [options]
  --audio-root DIR           WAV paths resolve inside this directory (default: manifest directory)
  --dry-run                  Verify schema, corpus/WAV SHA256, PCM and gold parser slots; no network
  --base URL                 Loopback IP + isolated port (default http://127.0.0.1:8089)
  --run-label TEXT           Required for replay; identifies this experiment
  --runtime-label TEXT       Required for replay; operator-declared model/config/image identity
  --trailing-silence-ms N     0..2000 (default 1000); sole controllable transport factor
  --output FILE              New JSON evidence file; refuses overwrite (otherwise stdout)
  --help                     Print this help, no network or files
Exit: 0 = validated/all cases passed; 1 = failed case, invalid input or runtime failure.
No deck executor, model downloads, cloud API or service changes. WAVs remain local.
ASR replay bypasses the browser microphone. Complete command and slots are both required.
`;

export async function main(argv, dependencies = {}) {
  const emit = dependencies.emit ?? (value => console.log(value));
  try {
    if (argv.length === 1 && argv[0] === '--help') { emit(help); return 0; }
    const options = {}; const allowed = new Set(['manifest', 'audio-root', 'base', 'run-label', 'runtime-label', 'trailing-silence-ms', 'output', 'dry-run']);
    for (let i = 0; i < argv.length; i++) {
      const key = argv[i].replace(/^--/, '');
      assert.ok(argv[i].startsWith('--') && allowed.has(key) && !Object.hasOwn(options, key), `Unknown or repeated option: ${argv[i]}`);
      if (key === 'dry-run') options[key] = true;
      else { assert.ok(argv[i + 1] && !argv[i + 1].startsWith('--'), `Missing value: ${argv[i]}`); options[key] = argv[++i]; }
    }
    text(options.manifest, '--manifest');
    const base = localEndpoint(options.base ?? 'http://127.0.0.1:8089');
    const silence = options['trailing-silence-ms'] ?? '1000';
    assert.ok(/^\d+$/.test(silence) && Number(silence) <= 2000, 'Invalid trailing silence');
    if (!options['dry-run']) { text(options['run-label'], '--run-label', 200); text(options['runtime-label'], '--runtime-label', 2000); }
    if (options.output) {
      try { await fs.lstat(options.output); throw Error('Output already exists; evidence is never overwritten'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    const corpus = await loadCorpus(options.manifest, options['audio-root']);
    const report = options['dry-run'] ? {result: 'VALIDATED_NOT_RUN', historical_baseline: historicalBaseline,
      corpus_id: corpus.manifest.corpus_id, corpus_sha256: corpus.manifest.corpus_sha256,
      manifest_sha256: corpus.manifest_sha256, cases: corpus.manifest.cases.length, speakers: corpus.manifest.speakers,
      asr_measured: false} : await evaluate(corpus, {base, trailingSilenceMs: Number(silence),
        runLabel: options['run-label'], runtimeLabel: options['runtime-label']}, dependencies.replay);
    const output = JSON.stringify(report, null, 2);
    if (options.output) await fs.writeFile(options.output, `${output}\n`, {flag: 'wx'});
    emit(options.output ? JSON.stringify({result: report.result, output: path.resolve(options.output), summary: report.summary}) : output);
    return report.result === 'FAIL' ? 1 : 0;
  } catch (error) { emit(JSON.stringify({result: 'FAIL', error: String(error), historical_baseline: historicalBaseline})); return 1; }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  process.exitCode = await main(process.argv.slice(2));
}
