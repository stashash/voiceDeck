import React, { useMemo, useRef, useState } from 'react';
import { analyzeDatasetBundle, DatasetBundlePlanResponse, DatasetTablePlan, errorText, VisualizationCandidate } from './api';

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
  histogram: 'Распределение', scatter: 'Связь показателей', grouped_column: 'Факт и план', kpi: 'Показатель',
};

function candidateKey(candidate: VisualizationCandidate) {
  return `${candidate.kind}:${candidate.required_fields.join('|')}`;
}

function roleLabel(column: DatasetTablePlan['profile']['columns'][number]) {
  const roles = column.role_candidates.map(role => ({
    numeric: 'показатель', category: 'категория', datetime: 'время', identifier: 'идентификатор',
  }[role] ?? role));
  return roles.length ? roles.join(', ') : column.type === 'empty' ? 'пусто' : column.type;
}

export function SemanticDataPlan() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [goal, setGoal] = useState('');
  const [result, setResult] = useState<DatasetBundlePlanResponse | null>(null);
  const [activeDataset, setActiveDataset] = useState(0);
  const [activeCandidate, setActiveCandidate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const dataset = result?.datasets[activeDataset];
  const selectedCandidate = useMemo(() => {
    if (!dataset) return null;
    return dataset.plan.candidates.find(candidate => candidateKey(candidate) === activeCandidate)
      ?? dataset.plan.selected_candidate;
  }, [dataset, activeCandidate]);

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
    setActiveCandidate('');
    setError('');
  }

  function removeFile(index: number) {
    setFiles(current => current.filter((_, i) => i !== index));
    setResult(null);
    setActiveDataset(0);
    setActiveCandidate('');
  }

  async function analyze() {
    if (!files.length || busy) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const response = await analyzeDatasetBundle(files, goal);
      setResult(response);
      setActiveDataset(0);
      setActiveCandidate('');
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
      <button type="button" className="button" onClick={() => inputRef.current?.click()}>
        {files.length ? 'Добавить файлы' : 'Выбрать данные'}
      </button>
      <input ref={inputRef} type="file" hidden multiple accept=".csv,.xlsx,.json,.txt,.md,.markdown"
        onChange={event => { addFiles(event.target.files); event.target.value = ''; }}/>
      <label className="semantic-plan-goal">
        <span>Что хотите понять?</span>
        <select value={goal} onChange={event => { setGoal(event.target.value); setResult(null); }}>
          {GOALS.map(([label, value]) => <option key={label} value={value}>{label}</option>)}
        </select>
      </label>
      <button type="button" className="button primary" disabled={!files.length || busy} onClick={() => void analyze()}>
        {busy ? 'Анализирую…' : 'Проанализировать'}
      </button>
    </div>

    {!!files.length && <ul className="semantic-plan-files" aria-label="Выбранные файлы">
      {files.map((file, index) => <li key={`${file.name}:${file.size}:${file.lastModified}`}>
        <span>{file.name}</span><span>{(file.size / 1024).toFixed(0)} КБ</span>
        <button type="button" aria-label={`Убрать ${file.name}`} onClick={() => removeFile(index)}>×</button>
      </li>)}
    </ul>}

    {error && <p className="semantic-plan-error" role="alert">{error}</p>}
    {busy && <p className="semantic-plan-status" role="status">Проверяю структуру, пропуски и подходящие способы показа. Расчёты выполняются локально и детерминированно.</p>}

    {result && <div className="semantic-plan-result">
      <p className="semantic-plan-status" role="status">Найдено таблиц: {result.table_count}. Варианты ниже — проверяемые планы анализа, а не готовые слайды.</p>
      <div className="semantic-plan-datasets" role="tablist" aria-label="Наборы данных">
        {result.datasets.map((item, index) => <button key={`${item.file_name}:${item.sheet}:${index}`} type="button"
          role="tab" aria-selected={activeDataset === index} className={activeDataset === index ? 'selected' : ''}
          onClick={() => { setActiveDataset(index); setActiveCandidate(''); }}>
          <span>{item.file_name}{item.sheet ? ` · ${item.sheet}` : ''}</span>
          <small>{item.rows} строк · {item.columns} столбца</small>
        </button>)}
      </div>

      {dataset && <>
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
            onClick={() => setActiveCandidate(candidateKey(candidate))}>
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
        <p className="semantic-plan-footnote">Пока это анализ и выбор смысла. Перенос выбранного варианта в редактируемый слайд подключается отдельным следующим шагом.</p>
      </>}
    </div>}
  </section>;
}
