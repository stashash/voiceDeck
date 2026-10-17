import React, { useMemo, useRef, useState } from 'react';
import { DatasetTablePlan, errorText, VisualizationCandidate } from './api';
import { analyzePersistedBundle, candidateKey, DatasetSelection, PersistedBundle, selectedCandidates } from './datasetBundle';

const MAX_FILES = 7;
const MAX_FILE_BYTES = 1024 * 1024;
const ACCEPTED = /\.(csv|xlsx|json|txt|md|markdown)$/i;
const GOALS = [
  ['Автоматически определить', ''],
  ['Показать динамику', 'Показать динамику во времени'],
  ['Сравнить категории', 'Сравнить категории'],
  ['Показать доли', 'Показать доли структуры'],
  ['Показать распределение', 'Показать распределение значений'],
  ['Найти взаимосвязь', 'Найти взаимосвязь показателей'],
  ['Показать справочные данные', 'Показать справочную таблицу'],
  ['Посчитать число строк', 'Количество строк исходных данных'],
] as const;

const KIND_LABELS: Record<VisualizationCandidate['kind'], string> = {
  table: 'Таблица', line: 'Линия', bar: 'Столбцы горизонтально', column: 'Столбцы вертикально', pie: 'Доли',
  histogram: 'Распределение', scatter: 'Связь показателей', grouped_column: 'Факт и план', stacked_column: 'Состав с накоплением', kpi: 'Показатель',
};

function roleLabel(column: DatasetTablePlan['profile']['columns'][number]) {
  const roles = column.role_candidates.map(role => ({
    numeric: 'показатель', category: 'категория', datetime: 'время', identifier: 'идентификатор',
  }[role] ?? role));
  return roles.length ? roles.join(', ') : column.type === 'empty' ? 'пусто' : column.type;
}

export function SemanticDataPlan({ onCreate, creating = false }: { onCreate?: (bundle: PersistedBundle, selections: DatasetSelection[]) => Promise<void>; creating?: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [goal, setGoal] = useState('');
  const [result, setResult] = useState<PersistedBundle | null>(null);
  const [activeDataset, setActiveDataset] = useState(0);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [included, setIncluded] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const dataset = result?.datasets[activeDataset];
  const selectedCandidate = useMemo(() => {
    if (!dataset) return null;
    const key = selected[dataset.dataset_id] ?? candidateKey(dataset.plan.selected_candidate);
    return dataset.plan.candidates.find(candidate => candidateKey(candidate) === key)
      ?? dataset.plan.selected_candidate;
  }, [dataset, selected]);
  const selections = result ? selectedCandidates(result, selected, included) : [];
  const unsupported = result?.datasets.filter(item => included[item.dataset_id] !== false &&
    !item.plan.candidates.some(candidate => candidate.renderable && candidateKey(candidate) ===
      (selected[item.dataset_id] ?? candidateKey(item.plan.selected_candidate)))).length ?? 0;

  function addFiles(list: FileList | null) {
    if (!list) return;
    const selected = Array.from(list);
    const next = [...files];
    for (const file of selected) {
      if (!ACCEPTED.test(file.name)) {
        setError(`«${file.name}»: выберите CSV, XLSX, JSON, TXT или Markdown.`);
        return;
      }
      if (file.size > MAX_FILE_BYTES) {
        setError(`«${file.name}» больше 1 МБ. Уменьшите файл и добавьте его снова.`);
        return;
      }
      if (!next.some(existing => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) next.push(file);
    }
    if (next.length > MAX_FILES) {
      setError(`Можно добавить не больше ${MAX_FILES} файлов за один анализ.`);
      return;
    }
    setFiles(next);
    setResult(null);
    setActiveDataset(0);
    setSelected({}); setIncluded({});
    setError('');
  }

  function removeFile(index: number) {
    setFiles(current => current.filter((_, i) => i !== index));
    setResult(null);
    setActiveDataset(0);
    setSelected({}); setIncluded({});
  }

  async function analyze() {
    if (!files.length || busy) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const response = await analyzePersistedBundle(files, goal);
      setResult(response);
      setActiveDataset(0);
      setSelected({}); setIncluded({});
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return <section className="semantic-plan" aria-label="Раскрыть смысл данных">
    <div className="semantic-plan-heading">
      <div>
        <h2>Раскрыть смысл данных</h2>
        <p>Загрузите таблицы и задайте вопрос — сервис предложит, что показать и почему.</p>
      </div>
      <span className="semantic-plan-count">{files.length}/{MAX_FILES}</span>
    </div>

    <div className="semantic-plan-controls">
      <button type="button" className="button" disabled={busy || creating} onClick={() => inputRef.current?.click()}>
        {files.length ? 'Добавить файлы' : 'Выбрать данные'}
      </button>
      <input ref={inputRef} type="file" hidden multiple accept=".csv,.xlsx,.json,.txt,.md,.markdown"
        onChange={event => { addFiles(event.target.files); event.target.value = ''; }}/>
      <label className="semantic-plan-goal">
        <span>Что хотите понять?</span>
        <select value={goal} disabled={busy || creating} onChange={event => { setGoal(event.target.value); setResult(null); }}>
          {GOALS.map(([label, value]) => <option key={label} value={value}>{label}</option>)}
        </select>
      </label>
      <button type="button" className="button primary" disabled={!files.length || busy || creating} onClick={() => void analyze()}>
        {busy ? 'Анализирую…' : 'Проанализировать'}
      </button>
    </div>

    {!!files.length && <ul className="semantic-plan-files" aria-label="Выбранные файлы">
      {files.map((file, index) => <li key={`${file.name}:${file.size}:${file.lastModified}`}>
        <span>{file.name}</span><span>{(file.size / 1024).toFixed(0)} КБ</span>
        <button type="button" disabled={busy || creating} aria-label={`Убрать ${file.name}`} onClick={() => removeFile(index)}>×</button>
      </li>)}
    </ul>}

    {error && <p className="semantic-plan-error" role="alert">{error}</p>}
    {busy && <p className="semantic-plan-status" role="status">Проверяю структуру, пропуски и подходящие способы показа. Расчёты выполняются локально и детерминированно.</p>}

    {result && <div className="semantic-plan-result">
      <p className="semantic-plan-status" role="status">Найдено таблиц: {result.table_count}. Варианты ниже — проверяемые планы анализа, а не готовые слайды.</p>
      <div className="semantic-plan-datasets" role="tablist" aria-label="Наборы данных">
        {result.datasets.map((item, index) => <button key={`${item.file_name}:${item.sheet}:${index}`} type="button"
          role="tab" aria-selected={activeDataset === index} className={activeDataset === index ? 'selected' : ''}
          onClick={() => setActiveDataset(index)}>
          <span>{item.file_name}{item.sheet ? ` · ${item.sheet}` : ''}</span>
          <small>{item.rows} строк · {item.columns} столбца</small>
        </button>)}
      </div>

      {dataset && <>
        <label><input type="checkbox" checked={included[dataset.dataset_id] !== false} disabled={creating}
          onChange={event => setIncluded(current => ({ ...current, [dataset.dataset_id]: event.target.checked }))}/>
          Включить эту таблицу в презентацию</label>
        <div className="semantic-plan-profile">
          <div className="semantic-plan-profile-heading">
            <strong>Структура</strong><span>{dataset.rows} строк · {dataset.columns} столбца</span>
          </div>
          <ul>{dataset.profile.columns.map(column => <li key={column.name}>
            <span>{column.name}</span><small>{roleLabel(column)}{column.missing_count ? ` · ${column.missing_count} пропусков` : ''}</small>
          </li>)}</ul>
        </div>
        <h3>Варианты раскрытия</h3>
        <div className="semantic-plan-candidates">
          {dataset.plan.candidates.map(candidate => <button type="button" key={candidateKey(candidate)}
            aria-pressed={selectedCandidate === candidate} className={selectedCandidate === candidate ? 'selected' : ''}
            disabled={creating} onClick={() => setSelected(current => ({ ...current, [dataset.dataset_id]: candidateKey(candidate) }))}>
            <strong>{KIND_LABELS[candidate.kind]}</strong>
            <span>{candidate.reason}</span>
            {!candidate.renderable && <small>Рендерер этого типа ещё не подключён</small>}
          </button>)}
        </div>
        {selectedCandidate && <div className="semantic-plan-detail">
          <strong>Почему подходит</strong><p>{selectedCandidate.reason}</p>
          <p>Поля: {selectedCandidate.required_fields.join(', ') || 'все исходные поля без агрегации'}</p>
          {selectedCandidate.excluded_row_lines.length > 0 && <p>Строки с пропусками: {selectedCandidate.excluded_row_lines.join(', ')}</p>}
          {selectedCandidate.warnings.map(warning => <p key={warning} className="semantic-plan-warning">{warning}</p>)}
        </div>}
        {onCreate && <button type="button" className="button primary"
          disabled={busy || creating || !selections.length || unsupported > 0} onClick={() => void onCreate(result, selections)}>
          {creating ? 'Создаю презентацию…' : `Создать презентацию по выбранным таблицам (${selections.length})`}
        </button>}
        {unsupported > 0 && <p className="semantic-plan-warning">Для {unsupported} таблиц выбран неподдерживаемый тип. Выберите другой вариант или исключите эти таблицы.</p>}
        <p className="semantic-plan-footnote">Выбор сохраняется для каждой таблицы. Источники, охват и выбранные варианты будут переданы в одну презентацию.</p>
      </>}
    </div>}
  </section>;
}
