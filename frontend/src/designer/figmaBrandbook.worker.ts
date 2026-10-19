import { parseFigForBrandbook } from './figmaBrandbookParser';
import { extractFigTokens } from './figmaTokens';

self.onmessage = async (event: MessageEvent<{ bytes: ArrayBuffer; name: string }>) => {
  try {
    const { bytes, name } = event.data;
    if (bytes.byteLength > 20 * 1024 * 1024) throw new Error('Файл .fig больше 20 МБ.');
    const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    const result = extractFigTokens(parseFigForBrandbook(new Uint8Array(bytes)), name, sha256);
    self.postMessage({ ok: true, result });
  } catch (cause) {
    self.postMessage({ ok: false, error: `Не удалось прочитать .fig: ${cause instanceof Error ? cause.message : 'повреждённый файл'}` });
  }
};
