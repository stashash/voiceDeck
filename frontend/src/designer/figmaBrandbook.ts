import type { FigmaBrandbook } from './figmaTokens';

export const MAX_FIG_BYTES = 20 * 1024 * 1024;
export const FIG_TIMEOUT_MS = 12_000;

/** Parse offline in an interruptible worker; only extracted JSON reaches the service. */
export async function convertFigmaBrandbook(file: File): Promise<File> {
  if (file.size > MAX_FIG_BYTES) throw new Error('Файл .fig больше 20 МБ. Экспортируйте отдельную страницу брендбука.');
  if (!file.size) throw new Error('Файл .fig пуст.');
  const bytes = await file.arrayBuffer();
  const result = await new Promise<FigmaBrandbook>((resolve, reject) => {
    const worker = new Worker(new URL('./figmaBrandbook.worker.ts', import.meta.url), { type: 'module' });
    const finish = () => { clearTimeout(timer); worker.terminate(); };
    const timer = setTimeout(() => { finish(); reject(new Error('Разбор .fig превысил 12 секунд. Экспортируйте отдельную страницу брендбука.')); }, FIG_TIMEOUT_MS);
    worker.onmessage = event => {
      finish();
      if (event.data?.ok && event.data.result) resolve(event.data.result);
      else reject(new Error(event.data?.error || 'Не удалось прочитать .fig.'));
    };
    worker.onerror = () => { finish(); reject(new Error('Не удалось прочитать .fig. Файл повреждён или версия не поддерживается.')); };
    worker.postMessage({ bytes, name: file.name }, [bytes]);
  });
  return new File([JSON.stringify(result)], `${file.name}.tokens.json`, { type: 'application/json' });
}
