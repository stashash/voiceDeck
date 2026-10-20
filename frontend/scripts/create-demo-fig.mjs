// Original synthetic fixture, encoded locally with the installed MIT parser.
import { mkdirSync, writeFileSync } from 'node:fs';
import { zstdCompressSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { createEmptyFigDoc, encodeFigParts, assembleCanvasFig, createFigZip, parseFig } from 'openfig-core';

const doc = createEmptyFigDoc();
const parent = { guid: { sessionID: 0, localID: 1 }, position: 'a' };
const guid = localID => ({ sessionID: 99, localID });
const nodes = [
  { guid: guid(1), type: 'FRAME', name: 'Local Demo Brand', parentIndex: parent, size: { x: 1280, y: 720 },
    layoutGrids: [{ type: 'STRETCH', axis: 'X', visible: true, numSections: 6, offset: 64, gutterSize: 24, pattern: 'STRIPES' }] },
  { guid: guid(2), type: 'RECTANGLE', name: 'brand/background', parentIndex: parent,
    fillPaints: [{ type: 'SOLID', color: { r: 0.05, g: 0.08, b: 0.16, a: 1 }, opacity: 1 }] },
  { guid: guid(3), type: 'RECTANGLE', name: 'brand/accent', parentIndex: parent,
    fillPaints: [{ type: 'SOLID', color: { r: 0.15, g: 0.55, b: 0.95, a: 1 }, opacity: 1 }] },
  { guid: guid(4), type: 'TEXT', name: 'brand/heading', parentIndex: parent,
    fontName: { family: 'Play', style: 'Bold', postscript: 'Play-Bold' }, fontSize: 48, textData: { characters: 'Local demo' } },
  { guid: guid(5), type: 'TEXT', name: 'brand/body', parentIndex: parent,
    fontName: { family: 'Play', style: 'Regular', postscript: 'Play-Regular' }, fontSize: 32, textData: { characters: 'Original synthetic brandbook fixture' } },
];
doc.message.nodeChanges.push(...nodes);
const parts = encodeFigParts(doc);
const canvasFig = assembleCanvasFig({ ...parts, messageCompressed: zstdCompressSync(parts.messageRaw) });
const bytes = createFigZip({ canvasFig, meta: { file_name: 'Local Demo Brand', provenance: 'Original synthetic VoiceDeck fixture; no external assets.' } });
const target = fileURLToPath(new URL('../../examples/brandbooks/local-demo.fig', import.meta.url));
mkdirSync(fileURLToPath(new URL('../../examples/brandbooks/', import.meta.url)), { recursive: true });
writeFileSync(target, bytes);
console.log(`${target}: ${bytes.length} bytes, ${parseFig(bytes).nodes.length} nodes (real Kiwi/Zstd canvas in ZIP)`);
