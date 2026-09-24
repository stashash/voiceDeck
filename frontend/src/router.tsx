import React, { lazy, Suspense, useEffect, useState } from 'react';
import Nav from './layout/Nav';

// Экраны версии 2 (docs/design/app-v2-contract.md, поток 3). Адреса:
// #/, #/decks/<id>, #/decks/<id>/edit/<variant>, #/design-systems[...], #/live, #/audience/<сессия>, #/settings.
const HomePage = lazy(() => import('./pages/HomePage'));
const GenerationPage = lazy(() => import('./pages/GenerationPage'));
const EditPage = lazy(() => import('./pages/EditPage'));
const DesignSystemsPage = lazy(() => import('./pages/DesignSystemsPage'));
const LivePage = lazy(() => import('./pages/LivePage'));
const AudiencePage = lazy(() => import('./stage/AudiencePage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

export type PageProps = { id?: string };

function useHash() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return hash;
}

export function Router() {
  const hash = useHash();
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const [root, a, b, c] = parts;

  // Окно зала: только слайд и субтитры, без шапки разделов.
  if (root === 'audience') return <Suspense fallback={null}><AudiencePage id={a}/></Suspense>;

  let page: React.ReactNode = null;
  let tab = '';
  if (!root) { page = <HomePage/>; tab = ''; }
  else if (root === 'decks' && a && b === 'edit' && c) { page = <EditPage deckId={a} variant={c}/>; tab = ''; }
  else if (root === 'decks' && a) { page = <GenerationPage deckId={a}/>; tab = ''; }
  else if (root === 'design-systems') { page = <DesignSystemsPage id={a}/>; tab = 'design-systems'; }
  else if (root === 'live') { page = <LivePage/>; tab = 'live'; }
  else if (root === 'settings') { page = <SettingsPage/>; tab = 'settings'; }

  if (!page) { window.location.hash = '#/'; return null; }
  return <div className="page-shell">
    <Nav route={tab}/>
    <Suspense fallback={<div className="page-loading">Загрузка</div>}>{page}</Suspense>
  </div>;
}
