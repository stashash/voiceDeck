import React, { useRef, useState } from 'react';
import { ChartBar, ChartColumn, ChartLine, ChartPie, Hash, Paperclip, Sheet, Table2, X } from 'lucide-react';
import { InsightVisual, InsightsResponse, errorText, tableInsights } from './api';
import { plural } from './labels';

// Пределы те же, что проверяет сервис (designer/insights/table.py): ошибку видно до загрузки.
const MAX_BYTES = 1024 * 1024;
const ACCEPT = /\.(xlsx|csv)$/i;

export const VISUAL_NAME: Record<InsightVisual, string> = {
  column: 'Столбчатая диаграмма', bar: 'Линейчатая диаграмма', line: 'График',
  pie: 'Круговая диаграмма', table: 'Таблица', big_number: 'Крупное число',
};
const VISUAL_ICON: Record<InsightVisual, typeof Hash> = {
  column: ChartColumn, bar: ChartBar, line: ChartLine, pie: ChartPie, table: Table2, big_number: Hash,
};

/** Таблица к брифу: загрузка, подсказки сервиса и отмеченные автором выводы. */
export function useTableInsights() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<InsightsResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const briefRef = useRef('');

  function clear() {
    request.current?.abort();
    request.current = null;
    setFile(null); setResult(null); setSelected(new Set()); setError(''); setLoading(false);
  }

  async function load(next: File, useModel: boolean) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError('');
    try {
      const found = await tableInsights(next, briefRef.current, controller.signal, useModel);
      if (request.current !== controller) return;
      setResult(found);
      setSelected(new Set(found.suggestions.map(s => s.id)));
    } catch (e) {
      if (controller.signal.aborted) return;
      setFile(null);
      setError(errorText(e));
    } finally {
      if (request.current === controller) { request.current = null; setLoading(false); }
    }
  }

  async function attach(next: File, brief: string) {
    clear();
    if (!ACCEPT.test(next.name)) { setError(`«${next.name}»: нужен файл xlsx или csv`); return; }
    if (next.size > MAX_BYTES) { setError(`«${next.name}» больше 1 МБ: оставьте в таблице только нужный лист и строки`); return; }
    briefRef.current = brief;
    setFile(next);
    await load(next, true);
  }

  /** Долгий ответ модели: таблица остаётся, выводы сразу формулирует код. */
  function stop() {
    if (file) void load(file, false);
  }

  function toggle(id: string) {
    setSelected(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  const chosen = result ? result.suggestions.filter(s => selected.has(s.id)).map(s => s.id) : [];
  return { file, result, selected, loading, error, chosen, attach, clear, stop, toggle, dismissError: () => setError('') };
}

export type TableInsightsState = ReturnType<typeof useTableInsights>;

export function AttachTableButton({ onPick }: { onPick: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return <>
    <button type="button" className="picker-btn" aria-label="Прикрепить таблицу"
      title="Прикрепить таблицу: xlsx (первый лист) или csv до 1 МБ, до 2000 строк и 50 столбцов. Сервис подскажет, что из неё показать"
      onClick={() => input.current?.click()}>
      <Paperclip size={18} strokeWidth={1.5}/>
    </button>
    <input ref={input} type="file" accept=".xlsx,.csv" hidden
      onChange={e => { const next = e.target.files?.[0]; e.target.value = ''; if (next) onPick(next); }}/>
  </>;
}

export function TableChip({ state }: { state: TableInsightsState }) {
  if (!state.file) return null;
  const r = state.result;
  return <div className="table-chip">
    <Sheet size={16} strokeWidth={1.5} className="icon-muted"/>
    <span className="table-chip-name">{state.file.name}</span>
    {r && <span className="table-chip-meta">
      {r.sheet ? `лист «${r.sheet}», ` : ''}{plural(r.rows, 'строка', 'строки', 'строк')}, {plural(r.columns, 'столбец', 'столбца', 'столбцов')}
    </span>}
    <button type="button" className="button-icon table-chip-remove" aria-label="Убрать таблицу" title="Убрать таблицу"
      onClick={state.clear}><X size={16} strokeWidth={1.5}/></button>
  </div>;
}

export function InsightsList({ state }: { state: TableInsightsState }) {
  const r = state.result;
  if (!state.loading && !r && !state.error) return null;
  return <section className="insights" aria-label="Что показать из таблицы">
    <h2 className="insights-title">Что показать из таблицы</h2>
    {state.error && <div className="notice" role="alert" style={{ margin: 0 }}>{state.error}
      <button onClick={state.dismissError} aria-label="Закрыть сообщение">×</button></div>}
    {state.loading && <div className="insights-status" role="status">
      <span className="insights-spinner" aria-hidden="true"/>Ищу выводы в таблице
      <button type="button" className="button" onClick={state.stop}>Остановить</button>
    </div>}
    {r && !state.loading && r.note && <p className="insights-note">{r.note}
      {r.note.startsWith('Модель недоступна') && <> <a href="#/settings">Настроить агента</a></>}</p>}
    {r && !state.loading && <ul className="insights-list">
      {r.suggestions.map(s => {
        const Icon = VISUAL_ICON[s.visual] ?? Hash;
        const on = state.selected.has(s.id);
        const tip = `insight-source-${s.id}`;
        return <li key={s.id}>
          <label className={`insight-row${on ? '' : ' off'}`}>
            <input type="checkbox" checked={on} onChange={() => state.toggle(s.id)}/>
            <span className="insight-visual" title={VISUAL_NAME[s.visual]} aria-label={VISUAL_NAME[s.visual]}>
              <Icon size={18} strokeWidth={1.5}/>
            </span>
            <span className="insight-headline">{s.headline}</span>
            {/* Щелчок по числу открывает источник, а не снимает галочку строки. */}
            <span className="insight-number" tabIndex={0} aria-describedby={tip} onClick={e => e.preventDefault()}>
              {s.number}
              <span role="tooltip" id={tip} className="insight-source">Откуда: {s.source}. Расчёт: {s.formula}</span>
            </span>
          </label>
        </li>;
      })}
    </ul>}
  </section>;
}
