import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const output = fileURLToPath(new URL('./voice-factory-output/', import.meta.url));
const names = process.argv.slice(2);
if (!names.length) throw Error('Pass report basenames, e.g. acceptance-audio-final acceptance-stop-final');
const rows = [];
const p95 = values => values.length ? [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1] : null;
for (const name of names) {
  if (!/^[a-z0-9-]+$/.test(name)) throw Error('Only report basenames are accepted');
  const report = JSON.parse(await fs.readFile(path.join(output, `${name}.json`), 'utf8'));
  const corpus = report.cases.filter(c => c.name.startsWith('audio-') && c.name !== 'audio-reference-dictation');
  const recognizedMutations = report.cases.flatMap(c => c.steps.filter(s => s.timing.mutated && c.replay?.utterances?.includes(s.phrase)));
  rows.push({report: name, result: report.result, corpusPassed: corpus.filter(c => c.result === 'PASS').length,
    corpusTotal: corpus.length, completeCommandChecks: corpus.every(c => typeof c.completeTranscript === 'boolean'),
    referenceDictation: report.cases.find(c => c.name === 'audio-reference-dictation')?.result ?? 'NOT_RUN',
    textGroupsPassed: report.cases.filter(c => !c.name.startsWith('audio-') && c.result === 'PASS').length,
    acceptanceDeckId: report.acceptanceDeckId, latency: report.latency,
    recognizedMutationLatency: {samples: recognizedMutations.length,
      parserExecutorP95Ms: p95(recognizedMutations.map(s => s.timing.parserMs + s.timing.executorMs)),
      persistedReadIncludedP95Ms: p95(recognizedMutations.map(s => s.timing.parserMs + s.timing.executorMs + s.timing.persistedReadMs))},
    audio: corpus.map(c => ({id: c.name, result: c.result, expected: c.fixture?.text,
      recognized: c.replay?.utterances ?? [], completeTranscript: c.completeTranscript ?? null,
      action: c.recognizedAction, sha256: c.replay?.sha256,
      packetsSent: c.replay?.packetsSent, packetsAcknowledged: c.replay?.packetsAcknowledged,
      sourceAudioMs: c.replay?.sourceAudioMs, timing: c.replay?.timing, error: c.error ?? null}))});
}
const summary = {generatedAt: new Date().toISOString(), physicalMicrophone: 'NOT_TESTED', originalGeneration: 'Main-owned separate regression', reports: rows};
await fs.writeFile(path.join(output, 'acceptance-summary.json'), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(rows.map(({report, result, corpusPassed, corpusTotal, referenceDictation, textGroupsPassed, latency}) =>
  ({report, result, corpusPassed, corpusTotal, referenceDictation, textGroupsPassed,
    deterministicP95Ms: latency.deterministicP95Ms, savedStateRoundTripP95Ms: latency.savedStateRoundTripP95Ms})), null, 2));
