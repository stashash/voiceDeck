import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ArrowUp, Upload, Settings, Boxes, Check } from 'lucide-react';
import {
  AgentAssignments, AgentInfo, DeckListItem, DesignSystemListItem,
  absoluteUrl, createDeck, getAgentAssignments, listAgents, listDecks, listDesignSystemItems, setAgentAssignments,
} from '../designer/api';

type Popover = 'ds' | 'agent' | null;

function agentLabel(a: AgentInfo): string {
  return a.kind === 'local' ? a.name : a.name;
}

export default function HomePage() {
  const [brief, setBrief] = useState('');
  const [designSystems, setDesignSystems] = useState<DesignSystemListItem[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [assignments, setAssignments] = useState<AgentAssignments | null>(null);
  const [dsId, setDsId] = useState<string>('');
  const [agentId, setAgentId] = useState<string>('');
  const [recent, setRecent] = useState<DeckListItem[]>([]);
  const [open, setOpen] = useState<Popover>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listDesignSystemItems().then(items => { setDesignSystems(items); setDsId(prev => prev || items[0]?.id || ''); }).catch(() => {});
    listAgents().then(setAgents).catch(() => {});
    getAgentAssignments().then(a => { setAssignments(a); setAgentId(prev => prev || a.deck || ''); }).catch(() => {});
    listDecks().then(setRecent).catch(() => {});
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

  async function submit() {
    if (!ready || !dsId || !agentId || !brief.trim() || busy) return;
    setBusy(true); setError('');
    try {
      if (assignments && assignments.deck !== agentId) {
        const next = { ...assignments, deck: agentId };
        await setAgentAssignments(next);
        setAssignments(next);
      }
      const { deck_id } = await createDeck({ design_system_id: dsId, brief, variants: ['a', 'b', 'c'] });
      window.location.hash = `#/decks/${deck_id}`;
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return <main className="home-main">
    <h1 className="home-title">О чём будет презентация?</h1>
    <div className="brief-box" ref={boxRef}>
      <label htmlFor="brief" style={{ position: 'absolute', left: -9999 }}>Бриф, текст или идея презентации</label>
      <textarea id="brief" className="field" rows={6} value={brief} onChange={e => setBrief(e.target.value)}
        placeholder="Бриф, текст или одна идея. Например: итоги пилота потоковой загрузки для директоров направлений"/>
      {error && <div className="notice" role="alert" style={{ margin: 0 }}>{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
      <div className="brief-row">
        {ready ? <div className="brief-pickers">
          <button type="button" className={`picker-btn ${open === 'ds' ? 'open' : ''}`} aria-haspopup="listbox"
            aria-expanded={open === 'ds'} aria-label={`Дизайн-система: ${selectedDs?.name ?? ''}`}
            onClick={() => setOpen(v => v === 'ds' ? null : 'ds')}>
            {selectedDs?.preview ? <img className="picker-thumb" src={absoluteUrl(selectedDs.preview)} alt=""/> : <Boxes size={18} strokeWidth={1.5}/>}
            <span>{selectedDs?.name ?? 'Дизайн-система'}</span>
            <ChevronDown size={16} strokeWidth={1.5}/>
          </button>
          <button type="button" className={`picker-btn ${open === 'agent' ? 'open' : ''}`} aria-haspopup="listbox"
            aria-expanded={open === 'agent'} aria-label={`Агент: ${selectedAgent ? agentLabel(selectedAgent) : ''}`}
            onClick={() => setOpen(v => v === 'agent' ? null : 'agent')}>
            <Boxes size={18} strokeWidth={1.5}/>
            <span>{selectedAgent ? agentLabel(selectedAgent) : 'Агент'}</span>
            <ChevronDown size={16} strokeWidth={1.5}/>
          </button>
          {open === 'agent' && <div className="popover" role="presentation">
            {cliAgents.length > 0 && <div className="popover-group">
              <span className="popover-group-title">Локальный CLI</span>
              <ul role="listbox" aria-label="Локальный CLI" className="popover-list">
                {cliAgents.map(a => <li key={a.id} role="option" aria-selected={a.id === agentId}>
                  <button type="button" className={`popover-option ${a.id === agentId ? 'selected' : ''}`}
                    onClick={() => { setAgentId(a.id); setOpen(null); }}>
                    <Boxes size={18} strokeWidth={1.5}/>
                    <span className="popover-option-body"><span className="popover-option-title">{a.name}</span>
                      <span className="popover-option-sub">{a.detail}</span></span>
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
                    onClick={() => { setAgentId(a.id); setOpen(null); }}>
                    <Boxes size={18} strokeWidth={1.5}/>
                    <span className="popover-option-body"><span className="popover-option-title">{a.name}</span>
                      <span className="popover-option-sub">{a.detail}</span></span>
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
                    <span className="popover-option-sub">{d.patterns} образцов</span></span>
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
        <button type="button" className="fab" disabled={!ready || !brief.trim() || busy}
          aria-label="Создать презентацию" title={ready ? 'Создать презентацию' : 'Сначала нужны дизайн-система и агент'}
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
          <span className="recent-meta">{d.slides} слайдов, {dsById.get(d.design_system_id)?.name ?? d.design_system_id}</span>
        </a>)}
      </div>
    </section>}
  </main>;
}
