import {test} from 'node:test';
import assert from 'node:assert/strict';
import {isolatedUrl, readPcmWav} from './voice-factory-audio.mjs';

function wav(bytes = 1024) {
  const result = Buffer.alloc(44 + bytes);
  result.write('RIFF'); result.writeUInt32LE(result.length - 8, 4); result.write('WAVEfmt ', 8);
  result.writeUInt32LE(16, 16); result.writeUInt16LE(1, 20); result.writeUInt16LE(1, 22);
  result.writeUInt32LE(16000, 24); result.writeUInt32LE(32000, 28); result.writeUInt16LE(2, 32); result.writeUInt16LE(16, 34);
  result.write('data', 36); result.writeUInt32LE(bytes, 40); if (bytes) result.writeInt16LE(3276, 44);
  return result;
}

test('guard rejects production ports, remote hosts and embedded credentials', () => {
  assert.equal(isolatedUrl('http://127.0.0.1:8089', 8089), 'http://127.0.0.1:8089');
  for (const url of ['http://127.0.0.1:8088', 'http://127.0.0.1:8090', 'https://example.com:8089', 'http://user:pass@localhost:8089', 'http://localhost:8089/api', 'http://localhost:8089/?x=1']) {
    assert.throws(() => isolatedUrl(url, 8089));
  }
});

test('WAV validation accepts only real nonempty PCM with a truthful RIFF length', () => {
  assert.equal(readPcmWav(wav()).length, 1024);
  assert.throws(() => readPcmWav(wav().subarray(0, 100)));
  const silent = wav(); silent.fill(0, 44); assert.throws(() => readPcmWav(silent));
  assert.throws(() => readPcmWav(wav(0)));
});

test('WAV validation rejects float, stereo, wrong sample rate and inconsistent byte rate', () => {
  for (const [offset, value] of [[20, 3], [22, 2], [24, 22050], [28, 64000], [32, 4], [34, 32]]) {
    const data = wav(); data.writeUInt16LE(value, offset);
    assert.throws(() => readPcmWav(data));
  }
});

test('WAV validation never silently truncates an oversized fixture', () => {
  assert.throws(() => readPcmWav(wav(32000 * 46)), /45 seconds/);
});

test('unknown RIFF chunks are accepted with their padding, malformed lengths rejected', () => {
  const source = wav(), junk = Buffer.alloc(10); junk.write('JUNK'); junk.writeUInt32LE(1, 4);
  const result = Buffer.concat([source.subarray(0, 36), junk, source.subarray(36)]);
  result.writeUInt32LE(result.length - 8, 4);
  assert.equal(readPcmWav(result).length, 1024);
  result.writeUInt32LE(0xffffffff, 40);
  assert.throws(() => readPcmWav(result), /Truncated chunk/);
});
