import React from 'react';
import { Settings } from 'lucide-react';

const TABS: [string, string][] = [['', 'Презентации'], ['design-systems', 'Дизайн-системы'], ['live', 'Live-режим']];

/** Верхняя шапка разделов, общая для всех экранов кроме окна зала. Холст: Home.dc.html. */
export default function Nav({ route }: { route: string }) {
  return <nav className="nav" aria-label="Разделы">
    <div className="nav-tabs">
      {TABS.map(([id, title]) => <a key={id} className={`nav-tab ${route === id ? 'active' : ''}`} href={`#/${id}`}
        aria-current={route === id ? 'page' : undefined}>{title}</a>)}
    </div>
    <a className="button-icon" href="#/settings" aria-label="Настройки: агенты и модели" title="Агенты и модели">
      <Settings size={20} strokeWidth={1.5}/>
    </a>
  </nav>;
}
