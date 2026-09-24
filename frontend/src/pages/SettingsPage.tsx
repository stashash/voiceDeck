import React, { useEffect, useState } from 'react';
import { RotateCw, TerminalSquare, Boxes } from 'lucide-react';
import {
  AgentAssignments, AgentCheckResult, AgentInfo,
  checkAgent, getAgentAssignments, listAgents, setAgentAssignments,
} from '../designer/api';
import { agentOptionName } from '../designer/agentName';

type Tab = 'cli' | 'local';
const ASSIGNMENT_ROWS: [keyof AgentAssignments, string][] = [
  ['deck', 'Презентации'], ['live', 'Live-режим'], ['describe', 'Описание образцов дизайн-системы'],
];

function statusLine(check: AgentCheckResult | 'busy' | undefined): { text: string; tone: '' | 'ok' | 'warn' } {
  if (check === 'busy') return { text: 'Проверяю…', tone: '' };
  if (!check) return { text: '', tone: '' };
  if (check.ok) return { text: `Проверено: отвечает${check.images === false ? ', картинки не принимает' : check.images ? ', принимает картинки' : ''}`, tone: check.images === false ? '' : 'ok' };
  return { text: check.message, tone: 'warn' };
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('cli');
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [assignments, setAssignments] = useState<AgentAssignments | null>(null);
  const [checks, setChecks] = useState<Record<string, AgentCheckResult | 'busy'>>({});
  const [error, setError] = useState('');

  function reload() {
    listAgents().then(setAgents).catch(e => setError(String(e)));
    getAgentAssignments().then(setAssignments).catch(() => {});
  }
  useEffect(reload, []);

  const cliAgents = agents.filter(a => a.kind === 'cli');
  const localAgents = agents.filter(a => a.kind === 'local');

  async function runCheck(id: string) {
    setChecks(prev => ({ ...prev, [id]: 'busy' }));
    try { const result = await checkAgent(id); setChecks(prev => ({ ...prev, [id]: result })); }
    catch (e) { setChecks(prev => ({ ...prev, [id]: { ok: false, images: null, seconds: 0, message: String(e) } })); }
  }

  function assign(task: keyof AgentAssignments, agentId: string) {
    if (!assignments) return;
    const next = { ...assignments, [task]: agentId };
    setAssignments(next);
    setAgentAssignments(next).catch(e => setError(String(e)));
  }

  return <main className="settings-shell">
    <h1 style={{ fontSize: 28, fontWeight: 600 }}>Агенты и модели</h1>
    {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
    <div role="tablist" className="settings-tabs">
      <button type="button" role="tab" aria-selected={tab === 'cli'} className={`settings-tab ${tab === 'cli' ? 'active' : ''}`} onClick={() => setTab('cli')}>Локальный CLI</button>
      <button type="button" role="tab" aria-selected={tab === 'local'} className={`settings-tab ${tab === 'local' ? 'active' : ''}`} onClick={() => setTab('local')}>Локальная модель</button>
    </div>

    {tab === 'cli' ? <>
      <div className="settings-row">
        <span className="settings-hint">Сервис ищет CLI-агентов в PATH этой машины.</span>
        <button type="button" className="button" onClick={reload}><RotateCw size={18} strokeWidth={1.5}/>Искать снова</button>
      </div>
      <div className="agent-cards">
        {cliAgents.map(a => {
          const check = checks[a.id];
          const st = statusLine(check);
          return <div key={a.id} className="agent-card">
            <div className="agent-card-head">
              <span className="agent-icon"><TerminalSquare size={20} strokeWidth={1.5}/></span>
              <div className="agent-card-body">
                <span className="agent-card-name">{a.name}</span>
                <span className="agent-card-sub">{a.detail}</span>
              </div>
              {a.found
                ? <button type="button" className="button" disabled={check === 'busy'} onClick={() => runCheck(a.id)}>Проверить</button>
                : <a className="agent-install-link" href={`#install-${a.name}`}>Как установить</a>}
            </div>
            {st.text && <div className="agent-card-status-row"><span className={`agent-status ${st.tone}`}>{st.text}</span></div>}
            {a.found && <div className="agent-model-row">
              <label>Модель</label>
              <input type="text" placeholder="модель по умолчанию в CLI" defaultValue={a.model ?? ''}/>
            </div>}
          </div>;
        })}
        {!cliAgents.length && <p className="settings-hint">CLI-агенты не найдены.</p>}
      </div>
    </> : <>
      <p className="settings-hint">Модель работает на этой машине через OpenAI-совместимый сервер.</p>
      <div className="card">
        <div className="agent-card-head">
          <span className="agent-icon"><Boxes size={20} strokeWidth={1.5}/></span>
          <div className="agent-card-body">
            <span className="agent-card-name">LM Studio</span>
            <span className={`agent-status ${localAgents.length ? 'ok' : 'warn'}`}>{localAgents.length ? `Сервер отвечает, моделей: ${localAgents.length}` : 'Сервер недоступен'}</span>
          </div>
          <button type="button" className="button" disabled={!localAgents[0]} onClick={() => localAgents[0] && runCheck(localAgents[0].id)}>Проверить</button>
        </div>
        <div className="local-grid">
          <div className="local-field">
            <label>Адрес сервера</label>
            <input type="text" defaultValue="http://127.0.0.1:1234/v1"/>
          </div>
          <div className="local-field">
            <label>Модель для текста и картинок</label>
            <select disabled={!localAgents.length}>
              {localAgents.map(a => <option key={a.id} value={a.id}>{agentOptionName(a)}</option>)}
            </select>
          </div>
        </div>
      </div>
    </>}

    <div className="card assignments-card">
      <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Какой агент что делает</h2>
      {ASSIGNMENT_ROWS.map(([task, label]) => <div key={task} className="assignment-row">
        <label>{label}</label>
        <select value={assignments?.[task] ?? ''} onChange={e => assign(task, e.target.value)}>
          {agents.map(a => <option key={a.id} value={a.id}>{agentOptionName(a)}</option>)}
        </select>
      </div>)}
    </div>
  </main>;
}
