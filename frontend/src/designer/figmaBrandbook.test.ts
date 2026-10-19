import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseFig } from 'openfig-core';
import { extractFigTokens } from './figmaTokens';
import { convertFigmaBrandbook, FIG_TIMEOUT_MS, MAX_FIG_BYTES } from './figmaBrandbook';
import { uploadBrandbook } from './brandbookApi';
import { parseFigForBrandbook, interpretKiwiMessage } from './figmaBrandbookParser';

const fixture = readFileSync(new URL('../../../examples/brandbooks/local-demo.fig', import.meta.url));
const hash = createHash('sha256').update(fixture).digest('hex');

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('native offline Figma import', () => {
  it('decodes the real binary under strict CSP without Function or eval', () => {
    const expected = parseFig(fixture);
    vi.stubGlobal('Function', () => { throw new Error('CSP blocks Function'); });
    vi.stubGlobal('eval', () => { throw new Error('CSP blocks eval'); });
    const actual = parseFigForBrandbook(fixture);
    expect(actual.nodes).toEqual(expected.nodes);
    expect(extractFigTokens(actual, 'strict.fig', hash).tokens.colors).toHaveLength(2);
  });

  it('fails closed on truncated archives and excessive interpreted array counts', () => {
    expect(() => parseFigForBrandbook(fixture.subarray(0, 100))).toThrow();
    const schema = { package: null, definitions: [{ name: 'Message', kind: 'MESSAGE' as const, line: 0, column: 0,
      fields: [{ name: 'values', value: 1, type: 'uint', isArray: true, isDeprecated: false, line: 0, column: 0 }] }] };
    // Field 1, array count 200001 (unsigned varint), without allocating it.
    expect(() => interpretKiwiMessage(schema, new Uint8Array([1, 0xc1, 0x9a, 0x0c]))).toThrow('Слишком большой массив');
    expect(() => interpretKiwiMessage(schema, new Uint8Array([2, 0]))).toThrow('Неизвестное поле');
  });
  it('extracts concrete styles and explicit grid from a real encoded .fig archive', () => {
    expect(fixture.subarray(0, 2).toString()).toBe('PK');
    const doc = parseFig(fixture);
    expect(doc.header.prelude).toBe('fig-kiwi');
    const recovered = extractFigTokens(doc, 'local-demo.fig', hash);
    expect(recovered.tokens.colors).toEqual([{ hex: '0D1429', role: 'background' }, { hex: '268CF2', role: 'accent' }]);
    expect(recovered.tokens.fonts).toEqual([{ family: 'Play', role: 'heading' }, { family: 'Play', role: 'body' }]);
    expect(recovered.tokens.type_scale).toEqual([{ size_pt: 36, role: 'heading' }, { size_pt: 24, role: 'body' }]);
    expect(recovered.rules).toEqual({ grid_columns: 6, grid_gutter: 24 / 1280 });
    expect(recovered.tokens.guides_x).toHaveLength(7);
    expect(recovered.source.file_name).toBe('local-demo.fig');
    expect(recovered.source.sha256).toBe(hash);
  });

  it('does not invent a grid or type role when the file does not declare them', () => {
    const doc = parseFig(fixture);
    for (const node of doc.nodes) { delete node.layoutGrids; if (node.type === 'TEXT') node.name = 'Label'; }
    const result = extractFigTokens(doc, 'plain.fig', hash);
    expect(result.rules).toBeUndefined();
    expect(result.tokens.guides_x).toBeUndefined();
    expect(result.tokens.type_scale).toBeUndefined();
    expect(result.tokens.fonts).toEqual([{ family: 'Play', role: 'other' }]);
    expect(JSON.stringify(result.source.observed)).toContain('"size_px":48');
  });

  it('omits conflicting grids and unsupported transparent or gradient fills', () => {
    const doc = parseFig(fixture);
    const frame = doc.nodes.find(n => n.layoutGrids)!;
    frame.layoutGrids.push({ ...frame.layoutGrids[0], numSections: 3 });
    const swatch = doc.nodes.find(n => n.name === 'brand/accent')!;
    swatch.fillPaints![0].opacity = 0.5;
    const result = extractFigTokens(doc, 'conflict.fig', hash);
    expect(result.rules).toBeUndefined();
    expect(result.tokens.colors).toEqual([{ hex: '0D1429', role: 'background' }]);
    expect(result.source.warnings.join(' ')).toContain('разные колоночные сетки');
  });

  it('sends only extracted JSON to the service and terminates the offline worker', async () => {
    const terminate = vi.fn();
    class WorkerStub {
      onmessage?: (event: { data: unknown }) => void;
      terminate = terminate;
      postMessage(data: { bytes: ArrayBuffer; name: string }) {
        queueMicrotask(() => this.onmessage?.({ data: { ok: true, result: extractFigTokens(parseFig(new Uint8Array(data.bytes)), data.name, hash) } }));
      }
    }
    vi.stubGlobal('Worker', WorkerStub);
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ applied_fields: ['colors'] }) });
    vi.stubGlobal('fetch', fetch);
    await uploadBrandbook('test', new File([fixture], 'original.fig'), 'brand');
    const upload = fetch.mock.calls[0][1].body.get('file') as File;
    expect(upload.name).toBe('original.fig.tokens.json');
    const body = JSON.parse(await upload.text());
    expect(body.source.sha256).toBe(hash);
    expect(body.source.file_name).toBe('original.fig');
    expect(body.tokens.colors).toHaveLength(2);
    expect(terminate).toHaveBeenCalledOnce();
  });

  it('bounds input before reading and terminates a stalled worker on timeout', async () => {
    const arrayBuffer = vi.fn();
    await expect(convertFigmaBrandbook({ size: MAX_FIG_BYTES + 1, arrayBuffer } as unknown as File)).rejects.toThrow('20 МБ');
    expect(arrayBuffer).not.toHaveBeenCalled();
    const terminate = vi.fn();
    vi.stubGlobal('Worker', class { terminate = terminate; postMessage() {} });
    vi.useFakeTimers();
    const pending = convertFigmaBrandbook(new File([fixture], 'slow.fig'));
    const rejection = expect(pending).rejects.toThrow('12 секунд');
    await vi.advanceTimersByTimeAsync(FIG_TIMEOUT_MS + 1);
    await rejection;
    expect(terminate).toHaveBeenCalledOnce();
  });

  it('returns a readable worker error for malformed binary instead of uploading it', async () => {
    const postMessage = vi.fn();
    const workerScope: { onmessage?: (event: unknown) => Promise<void>; postMessage: typeof postMessage } = { postMessage };
    vi.stubGlobal('self', workerScope);
    await import('./figmaBrandbook.worker');
    await workerScope.onmessage!({ data: { bytes: new TextEncoder().encode('not a fig').buffer, name: 'bad.fig' } });
    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ ok: false, error: expect.stringContaining('Не удалось прочитать .fig') }));
    postMessage.mockClear();
    vi.stubGlobal('Function', () => { throw new Error('Production CSP disallows dynamic functions'); });
    vi.stubGlobal('eval', () => { throw new Error('Production CSP disallows eval'); });
    await workerScope.onmessage!({ data: { bytes: Uint8Array.from(fixture).buffer, name: 'local-demo.fig' } });
    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ ok: true, result: expect.objectContaining({
      source: expect.objectContaining({ sha256: hash, file_name: 'local-demo.fig' }),
      rules: { grid_columns: 6, grid_gutter: 24 / 1280 },
    }) }));
  });
});
