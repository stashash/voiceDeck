import React, { useEffect, useRef, useState } from 'react';
import { ChartBar, ChartColumn, ChartLine, ChartPie, Hash, Paperclip, Sheet, Table2, X } from 'lucide-react';
import { InsightView, InsightVisual, InsightsResponse, TablePreview, errorText, tableInsights, tablePreview } from './api';
import { plural } from './labels';

// Пределы те же, что проверяет сервис (designer/insights/table.py): ошибку видно до загрузки.
const MAX_BYTES = 1024 * 1024;
const ACCEPT = /\.(xlsx|csv)$/i;
// Обычное время ответа модели: по нему идёт полоса хода, пока выводы ищутся.
const EXPECTED_S = 20;

export const VISUAL_NAME: Record<InsightVisual, string> = {
  column: 'Столбчатая диаграмма', bar: 'Линейчатая диаграмма', line: 'График',
  pie: 'Круговая диаграмма', table: 'Таблица', big_number: 'Крупное число',
};
const VISUAL_ICON: Record<InsightVisual, typeof Hash> = {
  column: ChartColumn, bar: ChartBar, line: ChartLine, pie: ChartPie, table: Table2, big_number: Hash,
};

/** Подсказка узнаётся по кандидатам кода: после пересчёта под новый бриф снятая галочка остаётся снятой. */
const keyOf = (s: InsightView) => s.fact_ids?.length ? s.fact_ids.join('+') : s.id;

type Snapshot = { file: File; preview: TablePreview | null; result: InsightsResponse; selected: Set<string>; brief: string };

/** Таблица к брифу: загрузка, подсказки сервиса и отмеченные автором выводы. */
export function useTableInsights() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TablePreview | null>(null);
  const [result, setResult] = useState<InsightsResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [error, setError] = useState('');
  const [briefUsed, setBriefUsed] = useState('');
  const [removed, setRemoved] = useState<Snapshot | null>(null);
  const request = useRef<AbortController | null>(null);
  // Пересчёт под бриф запускается таймером: он читает свежие отметки, а не те, что были при его заводе.
  const latest = useRef({ file, result, selected, briefUsed });
  latest.current = { file, result, selected, briefUsed };

  function reset() {
    request.current?.abort();
    request.current = null;
    setFile(null); setPreview(null); setResult(null); setSelected(new Set()); setError(''); setLoading(false); setBriefUsed('');
  }

  function begin(): AbortController {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(''); setStartedAt(Date.now());
    return controller;
  }

  /** Ошибка файла убирает таблицу. Сбой связи при пересчёте, «Повторить» или «Остановить» таблицу и отметки
   *  оставляет: файл уже разобран, пересчёт запускал таймер, а не человек (приёмка 17.10). */
  function fail(controller: AbortController, e: unknown, keep: boolean) {
    if (controller.signal.aborted) return;
    if (!keep) { setFile(null); setPreview(null); setResult(null); }
    setError(errorText(e));
  }

  function finish(controller: AbortController) {
    if (request.current === controller) { request.current = null; setLoading(false); }
  }

  async function load(next: File, brief: string, useModel: boolean) {
    const { result: before, selected: chosenBefore } = latest.current;
    const off = new Set(before ? before.suggestions.filter(s => !chosenBefore.has(s.id)).map(keyOf) : []);
    const briefBefore = latest.current.briefUsed;
    const controller = begin();
    setBriefUsed(brief.trim());
    try {
      const found = await tableInsights(next, brief, controller.signal, useModel);
      if (request.current !== controller) return;
      setResult(found);
      setSelected(new Set(found.suggestions.filter(s => !off.has(keyOf(s))).map(s => s.id)));
    } catch (e) {
      const keep = (e as { status?: number }).status !== 422;
      // Список остался от прежнего брифа: отправка ждёт «Повторить», а не уходит со старыми выводами.
      if (keep && !controller.signal.aborted) setBriefUsed(briefBefore);
      fail(controller, e, keep);
    } finally {
      finish(controller);
    }
  }

  async function attach(next: File, brief: string) {
    reset();
    setRemoved(null);
    if (!ACCEPT.test(next.name)) { setError(`«${next.name}»: нужен файл xlsx или csv`); return; }
    if (next.size > MAX_BYTES) {
      const extra = /\.xlsx$/i.test(next.name) ? 'листы, строки и столбцы' : 'строки и столбцы';
      setError(`«${next.name}» больше 1 МБ: удалите лишние ${extra}`);
      return;
    }
    setFile(next);
    // Строки и столбцы и ошибка файла приходят сразу, до ответа модели (ред-тим 17.10).
    const controller = begin();
    try {
      const shape = await tablePreview(next, controller.signal);
      if (request.current !== controller) return;
      setPreview(shape);
    } catch (e) {
      // Старый сервис дизайнера без /insights/table: строки и столбцы придут вместе с подсказками.
      if ((e as { status?: number }).status !== 404) {
        fail(controller, e, false);
        finish(controller);
        return;
      }
    }
    await load(next, brief, true);
  }

  /** Долгий ответ модели: таблица остаётся, выводы сразу записываются без неё. */
  function stop() {
    if (file) void load(file, briefUsed, false);
  }

  /** После сбоя или остановки модели: тот же файл, текущий бриф, снова с моделью. */
  function retry(brief: string) {
    if (file) void load(file, brief, true);
  }

  /** Бриф правили после выводов модели: выводы считаются заново под новый бриф. */
  function refresh(brief: string) {
    const current = latest.current.file;
    if (current) void load(current, brief, true);
  }

  /** Подсказки модели собраны под другой бриф. Выводы без модели от брифа не зависят. */
  function isStale(brief: string) {
    return !!file && !!result && !result.note && brief.trim() !== briefUsed;
  }

  /** «Убрать таблицу» обратимо: подсказки и отметки остаются в памяти страницы до новой таблицы. */
  function clear() {
    if (file && result && !loading) setRemoved({ file, preview, result, selected, brief: briefUsed });
    reset();
  }

  function restore() {
    if (!removed) return;
    setFile(removed.file); setPreview(removed.preview); setResult(removed.result);
    setSelected(removed.selected); setBriefUsed(removed.brief); setRemoved(null);
  }

  function forget() {
    setRemoved(null);
  }

  function toggle(id: string) {
    setSelected(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  const chosen = result ? result.suggestions.filter(s => selected.has(s.id)).map(s => s.id) : [];
  // Колоду строит тот же агент, что и подсказки: недоступен он, колода тоже не соберётся.
  const modelDown = !!result?.note.startsWith('Модель недоступна');
  return {
    file, preview, result, selected, loading, startedAt, error, removed, chosen, modelDown,
    attach, clear, restore, forget, stop, retry, refresh, isStale, toggle, dismissError: () => setError(''),
  };
}

export type TableInsightsState = ReturnType<typeof useTableInsights>;

export function AttachTableButton({ onPick }: { onPick: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return <>
    <button type="button" className="picker-btn picker-icon" aria-label="Прикрепить таблицу"
      title="Прикрепить таблицу: xlsx (первый лист) или csv, до 1 МБ, 2000 строк, 50 столбцов. Подскажу, что из неё показать"
      onClick={() => input.current?.click()}>
      <Paperclip size={18} strokeWidth={1.5}/>
    </button>
    <input ref={input} type="file" accept=".xlsx,.csv" hidden
      onChange={e => { const next = e.target.files?.[0]; e.target.value = ''; if (next) onPick(next); }}/>
  </>;
}

export function TableChip({ state, onRetry }: { state: TableInsightsState; onRetry: () => void }) {
  // Ошибка файла стоит там же, где плашка файла, у скрепки, а не в списке подсказок.
  const error = state.error && <div className="notice table-error" role="alert">
    <span className="table-error-text">{state.error}</span>
    {state.file && !state.loading && <button type="button" className="button" onClick={onRetry}>Повторить</button>}
    <button type="button" className="button-icon" onClick={state.dismissError} aria-label="Закрыть сообщение" title="Закрыть">
      <X size={18} strokeWidth={1.5}/></button></div>;
  if (!state.file && state.removed) return <div className="table-chip removed" role="status">
    <Sheet size={18} strokeWidth={1.5} className="icon-muted"/>
    <span className="table-chip-name">Таблица «{state.removed.file.name}» убрана</span>
    <button type="button" className="button table-chip-undo" onClick={state.restore}>Вернуть</button>
    <button type="button" className="button-icon" aria-label="Закрыть" title="Закрыть" onClick={state.forget}>
      <X size={18} strokeWidth={1.5}/></button>
  </div>;
  if (!state.file) return error || null;
  const shape = state.preview ?? state.result;
  return <>{error}<div className="table-chip">
    <Sheet size={18} strokeWidth={1.5} className="icon-muted"/>
    <span className="table-chip-name">{state.file.name}</span>
    {shape && <span className="table-chip-meta">
      {shape.sheet ? `лист «${shape.sheet}», ` : ''}{plural(shape.rows, 'строка', 'строки', 'строк')}, {plural(shape.columns, 'столбец', 'столбца', 'столбцов')}
    </span>}
    <button type="button" className="button-icon table-chip-remove" aria-label="Убрать таблицу" title="Убрать таблицу"
      onClick={state.clear}><X size={18} strokeWidth={1.5}/></button>
  </div></>;
}

/** Ожидание по дизайн-системе: строка шага, прошедшие секунды и полоса хода. */
function Waiting({ state, refreshing }: { state: TableInsightsState; refreshing: boolean }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.round((now - state.startedAt) / 1000));
  const share = Math.min(seconds / EXPECTED_S, 0.95);
  const pace = seconds > EXPECTED_S ? 'дольше обычного' : `обычно до ${EXPECTED_S} секунд`;
  return <div className="insights-wait" role="status">
    <div className="insights-wait-row">
      <span>{refreshing ? 'Пересчитываю выводы под новый бриф' : 'Ищу выводы в таблице'}: {seconds} с, {pace}</span>
      <button type="button" className="button" onClick={state.stop}>Остановить</button>
    </div>
    <div className="insights-progress" aria-hidden="true"><span style={{ width: `${share * 100}%` }}/></div>
  </div>;
}

function Headline({ s, tip }: { s: InsightView; tip: string }) {
  const at = s.number_at;
  // Щелчок по числу открывает источник, а не снимает галочку строки.
  const number = <span className="insight-number" tabIndex={0} aria-describedby={tip} onClick={e => e.preventDefault()}>
    {at ? s.headline.slice(at[0], at[1]) : s.number}
    <span role="tooltip" id={tip} className="insight-source">Источник: {s.source}. Расчёт: {s.formula}</span>
  </span>;
  if (!at) return <span className="insight-headline">{s.headline} {number}</span>;
  return <span className="insight-headline">{s.headline.slice(0, at[0])}{number}{s.headline.slice(at[1])}</span>;
}

export function InsightsList({ state, brief, onRetry }: { state: TableInsightsState; brief: string; onRetry: () => void }) {
  const r = state.result;
  if (!state.loading && !r) return null;
  if (state.loading && !state.preview && !r) return null;
  const refreshing = state.loading && !!r;
  const modelNote = !!r?.note.startsWith('Модель');
  return <section className="insights" aria-label="Что показать из таблицы" aria-busy={state.loading}>
    <h2 className="insights-title">Что показать из таблицы</h2>
    {state.loading && <Waiting state={state} refreshing={refreshing}/>}
    {r && !state.loading && r.note && <p className="insights-note">
      <span className="insights-note-text">{r.note}
        {state.modelDown && <> Колода без модели не соберётся. <a href="#/settings" target="_blank" rel="noreferrer">Настроить агента</a></>}</span>
      {modelNote && <button type="button" className="button insights-retry" onClick={onRetry}>Повторить</button>}</p>}
    {r && <ul className={`insights-list${refreshing ? ' stale' : ''}`}>
      {r.suggestions.map(s => {
        const Icon = VISUAL_ICON[s.visual] ?? Hash;
        const on = state.selected.has(s.id);
        return <li key={s.id}>
          <label className={`insight-row${on ? '' : ' off'}`}>
            <input type="checkbox" checked={on} disabled={refreshing} onChange={() => state.toggle(s.id)}/>
            <span className="insight-visual" title={VISUAL_NAME[s.visual]} aria-label={VISUAL_NAME[s.visual]}>
              <Icon size={18} strokeWidth={1.5}/>
            </span>
            <Headline s={s} tip={`insight-source-${s.id}`}/>
            {!s.by_model && !r.note && <span className="insight-plain" title="Модель не предложила этот вывод: он записан по расчёту без неё">без модели</span>}
          </label>
        </li>;
      })}
    </ul>}
    {/* Под списком: строка не сдвигает список под курсором, когда снята последняя галочка (приёмка 17.10). */}
    {r && !state.loading && state.chosen.length === 0 && <p className="insights-note">{brief.trim()
      ? 'Ни один вывод не отмечен: колода соберётся только по брифу.'
      : 'Ни один вывод не отмечен: отметьте вывод или впишите бриф.'}</p>}
  </section>;
}
