import React, { useEffect, useState } from 'react';
import { RotateCw } from 'lucide-react';
import {
  AgentAssignments, AgentCheckResult, AgentInfo,
  checkAgent, getAgentAssignments, listAgents, setAgentAssignments,
} from '../designer/api';

type Tab = 'cli' | 'local';
const ASSIGNMENT_ROWS: [keyof AgentAssignments, string][] = [
  ['deck', 'Презентации'], ['live', 'Live-режим'], ['describe', 'Описание образцов дизайн-системы'],
];

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

  return <div className="settings-shell">
    <h1 style={{ fontSize: 20 }}>Агенты и модели</h1>
    {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
    <div className="settings-tabs">
      <button type="button" className={`settings-tab ${tab === 'cli' ? 'active' : ''}`} onClick={() => setTab('cli')}>Локальный CLI</button>
      <button type="button" className={`settings-tab ${tab === 'local' ? 'active' : ''}`} onClick={() => setTab('local')}>Локальная модель</button>
    </div>

    {tab === 'cli' ? <>
      <p className="settings-hint">Сервис ищет CLI-агентов в PATH этой машины.</p>
      <button type="button" className="button small" onClick={reload}><RotateCw size={14} strokeWidth={1.5}/>Искать снова</button>
      <div className="agent-list">
        {cliAgents.map(a => {
          const check = checks[a.id];
          return <div key={a.id} className="agent-row">
            <div>
              <div className="agent-name">{a.name}</div>
              <div className="agent-detail">{a.detail}</div>
            </div>
            <span className={`agent-status ${check && check !== 'busy' ? (check.ok ? 'ok' : 'warn') : ''}`}>
              {check === 'busy' ? 'Проверяю…' : check ? check.message : a.found ? '' : 'не найден в PATH'}
            </span>
            <button type="button" className="button small" disabled={!a.found || check === 'busy'} onClick={() => runCheck(a.id)}>Проверить</button>
          </div>;
        })}
        {!cliAgents.length && <p className="settings-hint">CLI-агенты не найдены.</p>}
      </div>
    </> : <>
      <p className="settings-hint">Модель работает на этой машине через OpenAI-совместимый сервер.</p>
      <div className="local-card">
        <div className="local-row">
          <strong>LM Studio</strong>
          <span className="agent-status">{localAgents.length ? `Сервер отвечает, моделей: ${localAgents.length}` : 'Сервер недоступен'}</span>
        </div>
        <div className="local-field">
          <label>Модель для текста и картинок</label>
          <select disabled={!localAgents.length}>
            {localAgents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <button type="button" className="button small" style={{ alignSelf: 'flex-start' }}
          disabled={!localAgents[0]} onClick={() => localAgents[0] && runCheck(localAgents[0].id)}>Проверить</button>
      </div>
    </>}

    <div className="assignments-block">
      <h2 style={{ fontSize: 16 }}>Какой агент что делает</h2>
      {ASSIGNMENT_ROWS.map(([task, label]) => <div key={task} className="assignment-row">
        <span>{label}</span>
        <select value={assignments?.[task] ?? ''} onChange={e => assign(task, e.target.value)}>
          {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>)}
    </div>
  </div>;
}
