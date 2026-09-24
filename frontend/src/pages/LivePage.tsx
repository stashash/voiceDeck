import React, { useEffect, useState } from 'react';
import { Mic, Square, MonitorPlay, ArrowRight, Boxes, Undo2 } from 'lucide-react';
import type { Slide } from '../store';
import { useSession } from '../stage/useSession';
import { AgentInfo, DesignSystemListItem, getAgentAssignments, listAgents, listDesignSystemItems } from '../designer/api';
import '../stage/stage.css';

const time = (ms: number) => `${Math.floor(ms / 60000).toString().padStart(2, '0')}:${Math.floor(ms / 1000 % 60).toString().padStart(2, '0')}`;

function SlidePreview({ slide }: { slide: Slide }) {
  if (slide.html) return <iframe className="live-frame" sandbox="" srcDoc={slide.html} title="Слайд"/>;
  return <div className="live-sketch">{slide.title && <h4>{slide.title}</h4>}<ul>{slide.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul></div>;
}

export default function LivePage() {
  const s = useSession();
  const [draft, setDraft] = useState('');
  const [designSystems, setDesignSystems] = useState<DesignSystemListItem[]>([]);
  const [agentName, setAgentName] = useState('');

  useEffect(() => {
    listDesignSystemItems().then(setDesignSystems).catch(() => {});
    Promise.all([listAgents(), getAgentAssignments()]).then(([agents, a]) => {
      const found = agents.find((x: AgentInfo) => x.id === a.live);
      if (found) setAgentName(found.name);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (document.activeElement as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space') { e.preventDefault(); s.fixDraft(); }
      else if (e.code === 'Backspace') { e.preventDefault(); s.removeLast(); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [s.fixDraft, s.removeLast]);

  function openHall() {
    if (!s.sessionId) return;
    window.open(`${location.pathname}${location.search}#/audience/${s.sessionId}`, '_blank');
  }

  const dsName = designSystems.find(d => d.id === s.designSystemId)?.name ?? s.designSystemId;
  const started = !!s.sessionId;
  const sentences = Object.values(s.state.sentences).sort((a, b) => a.t0 - b.t0);
  const duration = sentences.at(-1)?.t1 ?? 0;

  return <div className="live-shell">
    <div className="live-topbar">
      <div className="live-connection"><span className={s.connection === 'Подключено' ? 'on' : ''}/>{s.connection}</div>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{dsName || 'Дизайн-система не выбрана'}</span>
      <span style={{ fontSize: 13, color: 'var(--text-muted)', display: 'flex', gap: 6, alignItems: 'center' }}><Boxes size={16} strokeWidth={1.5}/>{agentName || 'Агент не назначен'}</span>
      {started && s.recording && <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text)' }}>Запись {time(duration)}</span>}
      <button type="button" className="button" style={{ marginLeft: started ? 0 : 'auto' }} title="Открыть окно зала" disabled={!s.sessionId} onClick={openHall}>
        <MonitorPlay size={16} strokeWidth={1.5}/>Окно для зала
      </button>
    </div>
    {s.error && <div className="notice" role="alert">{s.error}<button onClick={s.clearError} aria-label="Закрыть сообщение">×</button></div>}

    {!started ? <div className="live-idle">
      <button type="button" className="button primary" disabled={s.busy} onClick={() => void s.startRecording()}>
        <Mic size={18} strokeWidth={1.5}/>Начать запись
      </button>
      <span className="live-idle-hint">Браузер спросит доступ к микрофону</span>
      <div className="live-idle-composer">
        <span className="live-idle-hint">Или введите текст вместо микрофона</span>
        <form className="live-text-form" onSubmit={e => { e.preventDefault(); if (draft.trim()) { void s.sendText(draft); setDraft(''); } }}>
          <input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Текст вместо микрофона" maxLength={2000}/>
          <button className="button primary" disabled={!draft.trim() || s.busy} title="Отправить"><ArrowRight size={15} strokeWidth={1.5}/></button>
        </form>
      </div>
    </div> : <>
      <div className="live-main">
        <section className="live-slide-col">
          <h3>На экране зала</h3>
          <div className="live-slide-box">{s.current ? <SlidePreview slide={s.current}/> : <div className="live-slide-empty">Пока пусто</div>}</div>
          <button type="button" className="button small" disabled={!s.current} onClick={s.revertPrevious}><Undo2 size={14} strokeWidth={1.5}/>Вернуть прошлый</button>
        </section>
        <section className="live-slide-col">
          <h3>Следующий слайд из речи</h3>
          <div className="live-slide-box">{s.draft ? <SlidePreview slide={s.draft}/> : <div className="live-slide-empty">Ждём фрагмент</div>}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="button primary small" disabled={!s.draft} onClick={s.fixDraft}>Показать залу</button>
            <button type="button" className="button small" disabled={!s.current} onClick={s.removeLast}>Убрать</button>
          </div>
        </section>
      </div>
      <div className="live-transcript">
        <span style={{ color: 'var(--text-faint)' }}>Что вы сказали</span>
        {sentences.slice(-6).map(sent => <p key={sent.id}><time>{time(sent.t0)}</time>{sent.text}</p>)}
        {s.state.partial && <p className="live-partial">{s.state.partial}<span>▍</span></p>}
      </div>
      <div className="live-controls">
        {s.live
          ? <button type="button" className={`button ${s.recording ? 'primary' : ''}`} disabled={s.busy}
            onClick={() => void (s.recording ? s.stopRecording() : s.startRecording())}>
            {s.recording ? <Square size={15} strokeWidth={1.5}/> : <Mic size={16} strokeWidth={1.5}/>}{s.recording ? 'Стоп' : 'Запись'}
          </button>
          : <form className="live-text-form" onSubmit={e => { e.preventDefault(); if (draft.trim()) { void s.sendText(draft); setDraft(''); } }}>
            <input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Текст вместо микрофона" maxLength={2000}/>
            <button className="button primary" disabled={!draft.trim() || s.busy} title="Отправить"><ArrowRight size={15} strokeWidth={1.5}/></button>
          </form>}
        <span className="live-keys"><kbd>Пробел</kbd>показывает<kbd>Backspace</kbd>убирает</span>
      </div>
    </>}
  </div>;
}
