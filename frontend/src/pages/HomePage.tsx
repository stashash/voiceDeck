import React, { useEffect, useMemo, useRef, useState } from 'react';
import { plural } from '../designer/labels';
import { hashParam } from '../router';
import { ChevronDown, ArrowUp, Upload, Settings, Boxes, Check, X } from 'lucide-react';
import {
  AgentInfo, DeckListItem, DesignSystemListItem,
  absoluteUrl, createDeck, getAgentAssignments, listAgents, listDecks, listDesignSystemItems, setAgentAssignments, errorText
} from '../designer/api';
import { agentDisplayName, agentOptionName, agentOptionSub } from '../designer/agentName';
import { AttachTableButton, InsightsList, TableChip, useTableInsights } from '../designer/TableInsights';
import { SemanticDataPlan } from '../designer/SemanticDataPlan';
import { DatasetSelection, materializeDatasetBundle, PersistedBundle } from '../designer/datasetBundle';

type Popover = 'ds' | 'agent' | null;
// Холст: одна строка на четыре карточки, показаны две строки (Home.dc.html + правка координатора).
const RECENT_LIMIT = 8;

export default function HomePage() {
  const [brief, setBrief] = useState('');
  const [language, setLanguage] = useState<'ru' | 'en'>('ru');
  const [designSystems, setDesignSystems] = useState<DesignSystemListItem[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [dsId, setDsId] = useState<string>('');
  const [agentId, setAgentId] = useState<string>('');
  const [recent, setRecent] = useState<DeckListItem[]>([]);
  const [open, setOpen] = useState<Popover>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);
  const table = useTableInsights();

  useEffect(() => {
    listDesignSystemItems().then(items => { setDesignSystems(items); setDsId(prev => { const asked = hashParam('ds'); return prev || (asked && items.some(i => i.id === asked) ? asked : items[0]?.id) || ''; }); }).catch(() => {});
    listAgents().then(setAgents).catch(() => {});
    getAgentAssignments().then(a => setAgentId(prev => prev || a.deck || '')).catch(() => {});
    listDecks().then(items => setRecent(items.filter(d => d.slides > 0 && d.status !== 'error').slice(0, RECENT_LIMIT))).catch(() => {});
  }, []);

  // Агента могли сменить в настройках, открытых в соседней вкладке («Настроить агента»): при возврате
  // на главную список показывает того, кто на сервере ведёт подсказки и колоду (приёмка 17.10).
  useEffect(() => {
    function onFocus() {
      listAgents().then(setAgents).catch(() => {});
      getAgentAssignments().then(a => { if (a.deck) setAgentId(a.deck); }).catch(() => {});
    }
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(null);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const dsById = useMemo(() => new Map(designSystems.map(d => [d.id, d])), [designSystems]);
  const agentById = useMemo(() => new Map(agents.map(a => [a.id, a])), [agents]);
  const selectedDs = dsById.get(dsId);
  const selectedAgent = agentById.get(agentId);
  const cliAgents = agents.filter(a => a.kind === 'cli');
  const localAgents = agents.filter(a => a.kind === 'local');

  const ready = designSystems.length > 0 && agents.length > 0;

  /** Подсказки и колоду ведёт агент из списка под брифом: назначение сверяется со свежим состоянием сервера,
   *  а не с прочитанным при открытии страницы. */
  async function syncAgent(id: string) {
    if (!id) return;
    const current = await getAgentAssignments();
    if (current.deck !== id) await setAgentAssignments({ ...current, deck: id });
  }

  function chooseAgent(id: string) {
    setAgentId(id);
    setOpen(null);
    syncAgent(id).catch(e => setError(errorText(e)));
  }

  async function attachTable(file: File) {
    try { await syncAgent(agentId); } catch (e) { setError(errorText(e)); }
    await table.attach(file, brief);
  }

  /** «Повторить» после сбоя модели идёт к агенту, выбранному в списке сейчас. */
  async function retryTable() {
    try { await syncAgent(agentId); } catch (e) { setError(errorText(e)); }
    table.retry(brief);
  }

  const fromTable = !!table.result && table.chosen.length > 0;
  // Бриф правили после выводов модели: через 1,5 с выводы пересчитываются, до тех пор отправка ждёт.
  const stale = table.isStale(brief);
  useEffect(() => {
    if (!stale) return;
    const timer = window.setTimeout(() => table.refresh(brief), 1500);
    return () => window.clearTimeout(timer);
  }, [brief, stale]);
  const canSubmit = ready && (!!brief.trim() || fromTable) && !table.loading && !table.modelDown && !stale;
  const submitTitle = table.modelDown ? 'Модель недоступна: сначала настройте агента'
    : table.loading ? 'Подождите: выводы из таблицы ещё считаются'
    : stale ? 'Выводы собраны под прежний бриф: дождитесь пересчёта или нажмите «Повторить»'
    : !ready ? 'Сначала нужны дизайн-система и агент'
    : fromTable ? `Создать презентацию по брифу и ${plural(table.chosen.length, 'отмеченному выводу', 'отмеченным выводам', 'отмеченным выводам')}`
    : 'Создать презентацию по брифу';

  async function submit() {
    if (!canSubmit || !dsId || !agentId || busy) return;
    setBusy(true); setError('');
    try {
      await syncAgent(agentId);
      const text = brief.trim() || `Итоги по таблице «${table.result!.table_name}»`;
      const { deck_id } = await createDeck({
        design_system_id: dsId, brief: text, variants: ['a', 'b', 'c'], language,
        insights_id: fromTable ? table.result!.id : null, insight_ids: fromTable ? table.chosen : [],
      });
      window.location.hash = `#/decks/${deck_id}`;
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }

  async function createFromMeaning(bundle: PersistedBundle, selections: DatasetSelection[]) {
    if (!ready || !dsId || !agentId || busy) return;
    setBusy(true); setError('');
    try {
      await syncAgent(agentId);
      const materialized = await materializeDatasetBundle(bundle.id, selections);
      const presentationBrief = brief.trim() || `Покажите смысл выбранных данных: ${bundle.goal || 'общий обзор'}. Источники: ${bundle.datasets.filter(item => selections.some(selected => selected.dataset_id === item.dataset_id)).map(item => item.table_name).join(', ')}.`;
      const { deck_id } = await createDeck({
        design_system_id: dsId, brief: presentationBrief, variants: ['a', 'b', 'c'], language,
        insights_id: materialized.id, insight_ids: materialized.suggestions.map(item => item.id),
      });
      window.location.hash = `#/decks/${deck_id}`;
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  return <main className="home-main">
    <h1 className="home-title">О чём будет презентация?</h1>
    <div className="brief-box" ref={boxRef}>
      <label htmlFor="brief" style={{ position: 'absolute', left: -9999 }}>Бриф, текст или идея презентации</label>
      <textarea id="brief" className="field" rows={6} value={brief} onChange={e => setBrief(e.target.value)}
        placeholder="Бриф, текст или одна идея. Например: итоги пилота потоковой загрузки для директоров направлений"/>
      {error && <div className="notice" role="alert" style={{ margin: 0 }}>{error}
        <button type="button" className="button-icon" onClick={() => setError('')} aria-label="Закрыть сообщение" title="Закрыть">
          <X size={18} strokeWidth={1.5}/></button></div>}
      <TableChip state={table} onRetry={() => void retryTable()}/>
      <InsightsList state={table} brief={brief} onRetry={() => void retryTable()}/>
      <SemanticDataPlan brief={brief} onCreate={ready ? createFromMeaning : undefined} creating={busy}/>
      <div className="brief-row">
        <label>Язык презентации <select aria-label="Язык презентации" value={language}
          onChange={e => setLanguage(e.target.value as 'ru' | 'en')} disabled={busy}>
          <option value="ru">Русский</option><option value="en">English</option>
        </select></label>
        {ready ? <div className="brief-pickers">
          <AttachTableButton onPick={file => void attachTable(file)}/>
          <button type="button" className={`picker-btn ${open === 'ds' ? 'open' : ''}`} aria-haspopup="listbox"
            aria-expanded={open === 'ds'} aria-label={`Дизайн-система: ${selectedDs?.name ?? ''}`}
            onClick={() => setOpen(v => v === 'ds' ? null : 'ds')}>
            {selectedDs?.preview ? <img className="picker-thumb" src={absoluteUrl(selectedDs.preview)} alt=""/> : <Boxes size={18} strokeWidth={1.5}/>}
            <span>{selectedDs?.name ?? 'Дизайн-система'}</span>
            <ChevronDown size={16} strokeWidth={1.5}/>
          </button>
          <button type="button" className={`picker-btn ${open === 'agent' ? 'open' : ''}`} aria-haspopup="listbox"
            aria-expanded={open === 'agent'} aria-label={`Агент: ${selectedAgent ? agentDisplayName(selectedAgent) : ''}`}
            onClick={() => setOpen(v => v === 'agent' ? null : 'agent')}>
            <Boxes size={18} strokeWidth={1.5}/>
            <span>{selectedAgent ? agentDisplayName(selectedAgent) : 'Агент'}</span>
            <ChevronDown size={16} strokeWidth={1.5}/>
          </button>
          {open === 'agent' && <div className="popover" role="presentation">
            {cliAgents.length > 0 && <div className="popover-group">
              <span className="popover-group-title">Локальный CLI</span>
              <ul role="listbox" aria-label="Локальный CLI" className="popover-list">
                {cliAgents.map(a => <li key={a.id} role="option" aria-selected={a.id === agentId}>
                  <button type="button" className={`popover-option ${a.id === agentId ? 'selected' : ''}`}
                    onClick={() => chooseAgent(a.id)}>
                    <Boxes size={18} strokeWidth={1.5}/>
                    <span className="popover-option-body"><span className="popover-option-title">{agentOptionName(a)}</span>
                      <span className="popover-option-sub">{agentOptionSub(a)}</span></span>
                    {a.id === agentId && <Check size={18} strokeWidth={1.5}/>}
                  </button>
                </li>)}
              </ul>
            </div>}
            {localAgents.length > 0 && <div className="popover-group">
              <span className="popover-group-title">Локальная модель</span>
              <ul role="listbox" aria-label="Локальная модель" className="popover-list">
                {localAgents.map(a => <li key={a.id} role="option" aria-selected={a.id === agentId}>
                  <button type="button" className={`popover-option ${a.id === agentId ? 'selected' : ''}`}
                    onClick={() => chooseAgent(a.id)}>
                    <Boxes size={18} strokeWidth={1.5}/>
                    <span className="popover-option-body"><span className="popover-option-title">{agentOptionName(a)}</span>
                      <span className="popover-option-sub">{agentOptionSub(a)}</span></span>
                    {a.id === agentId && <Check size={18} strokeWidth={1.5}/>}
                  </button>
                </li>)}
              </ul>
            </div>}
            <div className="popover-sep"/>
            <a className="popover-link" href="#/settings"><Settings size={18} strokeWidth={1.5}/>Настроить агентов</a>
          </div>}
          {open === 'ds' && <div className="popover" role="presentation">
            <ul role="listbox" aria-label="Дизайн-системы" className="popover-list">
              {designSystems.map(d => <li key={d.id} role="option" aria-selected={d.id === dsId}>
                <button type="button" className={`popover-option ${d.id === dsId ? 'selected' : ''}`}
                  onClick={() => { setDsId(d.id); setOpen(null); }}>
                  {d.preview ? <img className="picker-thumb" src={absoluteUrl(d.preview)} alt=""/> : <Boxes size={18} strokeWidth={1.5}/>}
                  <span className="popover-option-body"><span className="popover-option-title">{d.name}</span>
                    <span className="popover-option-sub">{plural(d.patterns, 'образец', 'образца', 'образцов')}</span></span>
                  {d.id === dsId && <Check size={18} strokeWidth={1.5}/>}
                </button>
              </li>)}
            </ul>
          </div>}
        </div> : <div className="brief-pickers">
          <a className="home-first-btn" href="#/design-systems/new" aria-label="Дизайн-систем нет: создать из pptx">
            <Upload size={18} strokeWidth={1.5}/>Создать дизайн-систему
          </a>
          <a className="home-first-btn" href="#/settings" aria-label="Агент не подключён: открыть настройки">
            <Settings size={18} strokeWidth={1.5}/>Подключить агента
          </a>
        </div>}
        <button type="button" className="fab" disabled={!canSubmit || busy}
          aria-label="Создать презентацию" title={submitTitle}
          onClick={submit}>
          <ArrowUp size={20} strokeWidth={1.5} color="var(--accent-ink)"/>
        </button>
      </div>
    </div>
    {recent.length > 0 && <section className="recent-section">
      <div className="recent-head"><h2>Недавние презентации</h2></div>
      <div className="recent-grid">
        {recent.map(d => <a key={d.id} className="recent-card" href={`#/decks/${d.id}/edit/a`}>
          {d.preview ? <img className="recent-thumb" src={absoluteUrl(d.preview)} alt=""/> : <div className="recent-thumb"/>}
          <span className="recent-title">{d.title}</span>
          <span className="recent-meta">{plural(d.slides, 'слайд', 'слайда', 'слайдов')}, {dsById.get(d.design_system_id)?.name ?? d.design_system_id}</span>
        </a>)}
      </div>
    </section>}
  </main>;
}
