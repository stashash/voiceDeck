import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {actionSlots, corpusHash, evaluate, historicalBaseline, loadCorpus, loadProductionParser,
  localEndpoint, localFetch, localWebSocket, main, normalizeTranscript, parseManifestJson, scoreCase, summarize, validateManifest} from './voice-asr-evaluate.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const temporaryRoot = path.join(root, '.voice-factory');
const hash = value => createHash('sha256').update(value).digest('hex');
const seal = manifest => { manifest.corpus_sha256 = corpusHash(manifest); return manifest; };

function wav(amplitude = 1000) {
  const value = Buffer.alloc(1068);
  value.write('RIFF'); value.writeUInt32LE(value.length - 8, 4); value.write('WAVEfmt ', 8);
  value.writeUInt32LE(16, 16); value.writeUInt16LE(1, 20); value.writeUInt16LE(1, 22);
  value.writeUInt32LE(16000, 24); value.writeUInt32LE(32000, 28); value.writeUInt16LE(2, 32); value.writeUInt16LE(16, 34);
  value.write('data', 36); value.writeUInt32LE(1024, 40); value.writeInt16LE(amplitude, 44);
  return value;
}

function manifest() {
  return seal({schema_version: 1, corpus_id: 'unit-impulse-not-speech', corpus_sha256: '',
    speakers: [{id: 'test-generator', kind: 'synthetic', split: 'development', provenance: 'Unit impulse; no speech or ASR accuracy evidence', consent: 'not-applicable'}],
    cases: [{id: 'next', speaker_id: 'test-generator', condition: 'Mocked transcript only', wav: 'next.wav', sha256: hash(wav()),
      expected: {transcript: 'Следующий слайд', action: 'next', target: {slide: null, element: null}, arguments: {}}}]});
}

async function fixture(t, data = manifest(), bytes = wav()) {
  await fs.mkdir(temporaryRoot, {recursive: true});
  const directory = await fs.mkdtemp(path.join(temporaryRoot, 'asr-eval-test-'));
  t.after(async () => {
    const relative = path.relative(await fs.realpath(temporaryRoot), await fs.realpath(directory));
    assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative));
    await fs.rm(directory, {recursive: true, force: true});
  });
  const file = path.join(directory, 'manifest.json');
  await fs.writeFile(file, JSON.stringify(data));
  await fs.writeFile(path.join(directory, 'next.wav'), bytes);
  return {file, directory, data};
}

test('ambiguous duplicate JSON keys, including escaped names, are rejected', () => {
  assert.throws(() => parseManifestJson('{"id":"one","id":"two"}'), /Duplicate JSON key/);
  assert.throws(() => parseManifestJson('{"items":[{"id":1,"\\u0069d":2}]}'), /Duplicate JSON key/);
  assert.deepEqual(parseManifestJson('{"items":[{"id":"[}:,"},{"id":"ok"}]}'), {items: [{id: '[}:,'}, {id: 'ok'}]});
});

test('strict manifest rejects damaged metadata and split leakage before audio replay', () => {
  assert.equal(validateManifest(manifest()).cases.length, 1);
  const corruptions = [
    data => { data.schema_version = 2; },
    data => { data.speakers[0].kind = 'unknown'; },
    data => { data.speakers[0].split = 'train'; },
    data => { data.speakers[0].kind = 'human'; },
    data => { data.speakers.push({...data.speakers[0], split: 'holdout'}); },
    data => { data.cases[0].speaker_id = 'missing'; },
    data => { data.cases[0].sha256 = 'bad'; },
    data => { data.cases[0].expected.target.element = 1.5; },
    data => { delete data.cases[0].expected.transcript; },
    data => { data.cases[0].expected.arguments = []; },
    data => { data.cases[0].expected.arguments = JSON.parse('{"__proto__":{}}'); },
    data => { data.cases[0].expected.arguments.value = Infinity; },
    data => { data.cases[0].unexpected = true; },
    data => { data.cases.push({...structuredClone(data.cases[0]), id: 'duplicate', wav: 'another.wav'}); },
    data => { data.cases.push({...structuredClone(data.cases[0]), sha256: 'f'.repeat(64), wav: 'another.wav'}); },
    data => { data.cases = []; },
  ];
  for (const corrupt of corruptions) { const data = manifest(); corrupt(data); seal(data); assert.throws(() => validateManifest(data)); }
  const changed = manifest(); changed.cases[0].expected.transcript += ' лишнее';
  assert.throws(() => validateManifest(changed), /Corpus hash mismatch/);
});

test('paths reject absolute, remote and traversal audio references', () => {
  for (const value of ['../secret.wav', '/secret.wav', 'C:/secret.wav', '\\\\host\\share\\secret.wav', 'a/../../secret.wav', 'https://example.com/a.wav', 'a//b.wav', 'a/./b.wav']) {
    const data = manifest(); data.cases[0].wav = value; seal(data);
    assert.throws(() => validateManifest(data), /relative contained path/);
  }
});

test('loadCorpus validates exact bytes, PCM and independently supplied gold slots', async t => {
  const {file, directory} = await fixture(t);
  const corpus = await loadCorpus(file);
  assert.equal(corpus.manifest_sha256, hash(await fs.readFile(file)));
  assert.deepEqual(corpus.files.get('next'), wav());
  await fs.writeFile(path.join(directory, 'next.wav'), wav(2000));
  await assert.rejects(loadCorpus(file), /WAV hash mismatch/);
  const badPcm = wav(); badPcm.writeUInt32LE(44100, 24);
  const data = manifest(); data.cases[0].sha256 = hash(badPcm); seal(data);
  await fs.writeFile(file, JSON.stringify(data)); await fs.writeFile(path.join(directory, 'next.wav'), badPcm);
  await assert.rejects(loadCorpus(file));
  const wrongGold = manifest(); wrongGold.cases[0].expected.action = 'previous'; seal(wrongGold);
  await fs.writeFile(file, JSON.stringify(wrongGold)); await fs.writeFile(path.join(directory, 'next.wav'), wav());
  await assert.rejects(loadCorpus(file), /gold labels/);
  await fs.writeFile(file, '{broken JSON');
  await assert.rejects(loadCorpus(file), SyntaxError);
});

test('symlink directories cannot escape the audio root', async t => {
  const data = manifest(); data.cases[0].wav = 'outside/next.wav'; seal(data);
  const local = await fixture(t, data), outside = await fixture(t);
  await fs.symlink(outside.directory, path.join(local.directory, 'outside'), process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(loadCorpus(local.file), /escapes audio root/);
});

test('speaker consent and disjoint splits are explicit and human metrics never mix with synthetic', () => {
  const data = manifest();
  data.speakers.push({id: 'person-one', kind: 'human', split: 'holdout', provenance: 'Consented local recording', consent: 'recording-consented'});
  data.cases.push({...structuredClone(data.cases[0]), id: 'human-case', speaker_id: 'person-one', wav: 'person.wav', sha256: 'a'.repeat(64)});
  assert.equal(validateManifest(seal(data)).speakers.length, 2);
  const good = {complete_command: true, transcript_match: true, slots: {action: true, target: true, arguments: true}};
  const result = summarize([{...good, speaker_id: 'tts', source_kind: 'synthetic', split: 'development'},
    {...good, speaker_id: 'person-one', source_kind: 'human', split: 'holdout', complete_command: false, slots: {action: true, target: false, arguments: false}}]);
  assert.equal(result.by_kind_and_split.length, 2);
  assert.equal(result.by_kind_and_split[1].complete_command_rate, 0);
  assert.deepEqual(result.by_kind_and_split[1].slot_errors, {action: 0, target: 1, arguments: 1});
  assert.equal(result.complete_command_rate, undefined);
});

test('real parser scoring rejects incomplete commands, extra segments and wrong target/arguments', async () => {
  const parse = await loadProductionParser();
  const item = manifest().cases[0];
  assert.equal(scoreCase(item, ['Следующий слайд.'], parse).complete_command, true);
  assert.equal(scoreCase(item, ['Следующий'], parse).complete_command, false);
  assert.equal(scoreCase(item, ['Следующий слайд', 'Удали слайд'], parse).complete_command, false);
  assert.equal(scoreCase(item, [], parse).complete_command, false);
  const literal = {expected: {transcript: 'На слайде 2 выбери элемент 3, замени текст на Стоп 24!', action: 'text',
    target: {slide: 2, element: 3}, arguments: {text: 'Стоп 24!'}}};
  assert.equal(scoreCase(literal, [literal.expected.transcript], parse).complete_command, true);
  assert.equal(scoreCase(literal, [literal.expected.transcript.replace('элемент 3', 'элемент 4')], parse).slots.target, false);
  assert.equal(scoreCase(literal, [literal.expected.transcript.replace('Стоп 24!', 'Стоп 25!')], parse).slots.arguments, false);
  assert.equal(scoreCase(literal, [literal.expected.transcript.replace('Стоп', 'стоп')], parse).slots.arguments, false);
  assert.deepEqual(actionSlots(parse('Выбери элемент один')), {action: 'element', target: {slide: null, element: 1}, arguments: {}});
  assert.notEqual(normalizeTranscript('не удали'), normalizeTranscript('удали'));
  assert.notEqual(normalizeTranscript('2.5'), normalizeTranscript('25'));
  assert.notEqual(normalizeTranscript('одиннадцать'), normalizeTranscript('1надцать'));
});

test('local endpoint adapter remaps HTTP and WebSocket while blocking cloud, production and redirects', async () => {
  assert.equal(localEndpoint('http://127.0.0.1:18089'), 'http://127.0.0.1:18089');
  assert.equal(localEndpoint('http://[::1]:18089'), 'http://[::1]:18089');
  for (const base of ['http://127.0.0.1:8088', 'http://127.0.0.1:8090', 'http://127.0.0.1:5174', 'https://example.com', 'http://192.168.0.1:8089', 'http://localhost:8089', 'http://user:password@127.0.0.1:8089', 'http://127.0.0.1:8089/path']) {
    assert.throws(() => localEndpoint(base));
  }
  const calls = [];
  const guarded = localFetch('http://127.0.0.1:18089', async (url, init) => { calls.push({url, init}); return {}; });
  await guarded('http://127.0.0.1:8089/health', {redirect: 'follow'});
  assert.equal(calls[0].url, 'http://127.0.0.1:18089/health'); assert.equal(calls[0].init.redirect, 'error');
  assert.throws(() => guarded('https://example.com/upload'));
  assert.throws(() => guarded('http://127.0.0.1:8089/decks/user'));
  assert.throws(() => guarded('http://user:pass@127.0.0.1:8089/health'));
  const Socket = localWebSocket('http://127.0.0.1:18089', class { constructor(url) { this.url = url; } });
  assert.equal(new Socket('ws://127.0.0.1:8089/ws/session').url, 'ws://127.0.0.1:18089/ws/session');
  assert.throws(() => new Socket('wss://example.com/audio'));
  assert.throws(() => new Socket('ws://127.0.0.1:8089/other'));
});

function mockEvidence(file, transcript) {
  return fs.readFile(file).then(bytes => ({sha256: hash(bytes), utterances: [transcript], packetsSent: 1, packetsAcknowledged: 1,
    mode: 'mock-only-not-asr', file, events: [{type: 'flushed'}]}));
}

test('evaluation preserves failed cases, actual transcripts, snapshot hashes and historical baseline', async t => {
  const {file, directory} = await fixture(t);
  const corpus = await loadCorpus(file);
  await fs.writeFile(path.join(directory, 'next.wav'), wav(3000));
  let snapshot;
  const originalFetch = globalThis.fetch, originalWebSocket = globalThis.WebSocket;
  const result = await evaluate(corpus, {runLabel: 'unit-mock', runtimeLabel: 'mock-only-not-real-asr', base: 'http://127.0.0.1:18089'}, async (source, options) => {
    snapshot = source;
    assert.equal(options.base, 'http://127.0.0.1:8089');
    assert.equal(hash(await fs.readFile(source)), corpus.manifest.cases[0].sha256);
    return mockEvidence(source, 'Следующий');
  });
  assert.equal(result.result, 'FAIL');
  assert.equal(result.endpoint, 'http://127.0.0.1:18089');
  assert.deepEqual(result.cases[0].utterances, ['Следующий']);
  assert.equal(result.cases[0].slots.action, true); assert.equal(result.cases[0].complete_command, false);
  assert.equal(result.historical_baseline.passed, 5); assert.equal(result.historical_baseline.total, 9);
  assert.equal(result.historical_baseline.newly_measured, false);
  assert.ok(result.not_measured.includes('execution_ms'));
  assert.equal(result.cases[0].replay.timing, undefined);
  assert.equal(globalThis.fetch, originalFetch); assert.equal(globalThis.WebSocket, originalWebSocket);
  await assert.rejects(fs.access(snapshot));
});

test('runtime failures count in denominators and do not manufacture latency or success', async t => {
  const {file} = await fixture(t);
  const corpus = await loadCorpus(file);
  const result = await evaluate(corpus, {runLabel: 'unit-error', runtimeLabel: 'mock'}, async () => { throw Error('ASR timeout'); });
  assert.equal(result.summary.failed_cases, 1);
  assert.equal(result.summary.by_speaker[0].replay_errors, 1);
  assert.equal(result.cases[0].parser_ms, null);
  assert.equal(result.cases[0].replay, undefined);
});

test('CLI help/dry validation are offline; errors and failed cases return exit 1; reports cannot overwrite evidence', async t => {
  const {file, directory} = await fixture(t);
  const logs = []; let replayCount = 0;
  const dependencies = {emit: value => logs.push(value), replay: async source => { replayCount++; return mockEvidence(source, 'Предыдущий слайд'); }};
  assert.equal(await main(['--help'], dependencies), 0);
  assert.equal(await main(['--manifest', file, '--dry-run'], dependencies), 0);
  assert.equal(JSON.parse(logs.at(-1)).result, 'VALIDATED_NOT_RUN'); assert.equal(replayCount, 0);
  assert.equal(await main(['--manifest', file, '--base', 'https://cloud.invalid', '--dry-run'], dependencies), 1);
  assert.equal(await main(['--manifest', file, '--dry-run', '--dry-run'], dependencies), 1);
  const output = path.join(directory, 'result.json');
  const args = ['--manifest', file, '--run-label', 'mock', '--runtime-label', 'mock-only', '--output', output];
  assert.equal(await main(args, dependencies), 1); assert.equal(replayCount, 1);
  const before = await fs.readFile(output);
  assert.equal(JSON.parse(before).result, 'FAIL');
  assert.equal(await main(args, dependencies), 1); assert.equal(replayCount, 1);
  assert.deepEqual(await fs.readFile(output), before);
  await fs.writeFile(file, '{not JSON');
  const processResult = spawnSync(process.execPath, ['scripts/voice-asr-evaluate.mjs', '--manifest', file, '--dry-run'], {cwd: root, encoding: 'utf8'});
  assert.equal(processResult.status, 1);
  assert.match(processResult.stdout, /"result":"FAIL"/);
  assert.equal(historicalBaseline.passed, 5);
});
