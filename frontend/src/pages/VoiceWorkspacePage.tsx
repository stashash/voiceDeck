import React, { useEffect, useState } from 'react';
import { createDeck, listDecks, listTrash, libraryAction, listDesignSystemItems, getDeckState, DeckListItem, DesignSystemListItem } from '../designer/api';
import EditPage from './EditPage';
import VoiceEditorPage from './VoiceEditorPage';
import { Plus, Search, Trash2, Copy, RefreshCw, FileText, Mic, ArrowLeft, LayoutTemplate, ArchiveRestore } from 'lucide-react';
import { absoluteUrl } from '../designer/api';
import './voiceWorkspace.css';

export default function VoiceWorkspacePage() {
  const [decks, setDecks] = useState<DeckListItem[]>([]);
  const [trash, setTrash] = useState<DeckListItem[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [selected, setSelected] = useState(() => localStorage.getItem('voice-workspace-selected') ?? '');
  const [search, setSearch] = useState('');
  const [variant, setVariant] = useState('a');
  const [view, setView] = useState<'deck' | 'new' | 'local' | 'trash'>('deck');
  const [brief, setBrief] = useState('');
  const [design, setDesign] = useState('');
  const [count, setCount] = useState(8);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<DeckListItem | null>(null);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => { if (selected) localStorage.setItem('voice-workspace-selected', selected); }, [selected]);
  async function reload() {
    const [items, removed] = await Promise.all([listDecks(), listTrash()]);
    setDecks(items); setTrash(removed);
    setSelected(id => items.some(d => d.id === id) ? id : items[0]?.id ?? '');
  }
  useEffect(() => {
    void reload().catch(e => setError(String(e))).finally(() => setLoading(false));
    void listDesignSystemItems().then(items => { setSystems(items); setDesign(items[0]?.id ?? ''); }).catch(e => setError(String(e)));
  }, []);
  useEffect(() => {
    if (!selected || view !== 'deck') return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setReady(false); setStatus('Загрузка презентации…');
    async function check() {
      try {
        const state = await getDeckState(selected);
        if (disposed) return;
        const available = Object.entries(state.variants).find(([, v]) => v.status === 'done');
        if (available) {
          setVariant(v => state.variants[v]?.status === 'done' ? v : available[0]);
          setReady(true); setStatus('');
          void listDecks().then(items => { if (!disposed) setDecks(items); }).catch(e => { if (!disposed) setError(String(e)); });
        } else if (Object.values(state.variants).some(v => v.status === 'running') || state.status === 'running') {
          setStatus('Создаём презентацию. Редактор откроется автоматически.');
          timer = setTimeout(() => void check(), 3000);
        } else setStatus(state.error || 'Презентация не готова. Откройте страницу генерации для подробностей.');
      } catch (e) { if (!disposed) setStatus(String(e)); }
    }
    void check();
    return () => { disposed = true; clearTimeout(timer); };
  }, [selected, view]);

  async function manage(id: string, action: 'delete' | 'restore' | 'copy') {
    setBusy(true); setError('');
    try {
      const result = await libraryAction(id, action);
      await reload(); setDeleting(null);
      if (result.deck_id) { setSelected(result.deck_id); setView('deck'); }
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const result = await createDeck({ design_system_id: design, brief: brief.trim(), slide_count: count, variants: ['a'] });
      await reload(); setSelected(result.deck_id); setVariant('a'); setView('deck'); setBrief('');
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  const current = decks.find(d => d.id === selected);
  const openDeck = (id: string) => { setSelected(id); setVariant('a'); setView('deck'); setDeleting(null); };
  const filtered = decks.filter(d => d.title.toLowerCase().includes(search.toLowerCase()));
  return <div className="voice-workspace">
    <aside className="vw-library" aria-label="Мои презентации">
      <div className="vw-brand"><span className="vw-brand-icon"><Mic size={19}/></span><div><strong>Голосовая студия</strong><small>Ваши идеи. Ваш голос.</small></div></div>
      <button className="vw-create" disabled={busy} onClick={() => setView('new')}><Plus size={18}/>Новая презентация</button>
      <label className="vw-search"><Search size={16}/><input aria-label="Поиск презентаций" placeholder="Найти презентацию" value={search} onChange={e => setSearch(e.target.value)}/></label>
      <div className="vw-section-label"><span>МОИ ПРЕЗЕНТАЦИИ · {decks.length}</span><button aria-label="Обновить список" title="Обновить список" disabled={busy} onClick={() => void reload().catch(e => setError(String(e)))}><RefreshCw size={15}/></button></div>
      <div className="vw-documents">
        {loading && <p className="vw-muted">Загружаем документы…</p>}
        {!loading && !filtered.length && <p className="vw-muted">{search ? 'Ничего не найдено' : 'Пока нет презентаций. Создайте первую выше.'}</p>}
        {filtered.map(d => <button key={d.id} disabled={busy} className={`vw-document ${view === 'deck' && selected === d.id ? 'is-active' : ''}`} aria-pressed={view === 'deck' && selected === d.id} onClick={() => openDeck(d.id)}>
          <div className="vw-preview">{d.preview ? <img src={absoluteUrl(d.preview)} alt=""/> : <LayoutTemplate size={26}/>}<span>{d.slides} слайдов</span></div>
          <strong>{d.title || 'Без названия'}</strong><small><span className={`vw-dot ${d.status === 'done' ? 'done' : ''}`}/>{d.status === 'done' ? 'Готова к редактированию' : d.status === 'running' ? 'Создаётся…' : 'Нужна проверка'}</small>
        </button>)}
      </div>
      <div className="vw-library-footer">
        <button className={view === 'local' ? 'is-active' : ''} onClick={() => setView('local')}><FileText size={17}/><span>Локальный черновик<small>Сохранён в этом браузере</small></span></button>
        <button className={view === 'trash' ? 'is-active' : ''} onClick={() => { setView('trash'); void reload().catch(e => setError(String(e))); }}><Trash2 size={17}/>Корзина<span className="vw-count">{trash.length}</span></button>
      </div>
    </aside>
    <main className="vw-main">
      <header className="vw-header"><div><span className="vw-eyebrow">ГОЛОСОВАЯ СТУДИЯ</span><h1>{view === 'new' ? 'Создать презентацию' : view === 'trash' ? 'Корзина' : view === 'local' ? 'Локальный черновик' : 'Редактор презентации'}</h1></div>
        {view === 'deck' && current && <div className="vw-actions"><button className="button" disabled={busy || current.status === 'running'} onClick={() => void manage(current.id, 'copy')}><Copy size={16}/>Создать копию</button><button className="button vw-delete" disabled={busy || current.status === 'running'} onClick={() => setDeleting(current)}><Trash2 size={16}/>Удалить</button></div>}
        {view !== 'deck' && selected && <button className="button" onClick={() => setView('deck')}><ArrowLeft size={16}/>К презентации</button>}
      </header>
      {error && <div className="vw-error" role="alert">{error}<button onClick={() => setError('')}>Закрыть</button></div>}
      <div className="vw-content">
        {view === 'new' && <div className="vw-form-wrap"><span className="vw-hero-icon"><LayoutTemplate size={30}/></span><h2>С чего начнём?</h2><p className="vw-muted">Опишите идею, выберите оформление. Готовую презентацию можно будет править голосом.</p><form className="vw-form" onSubmit={e => void create(e)}>
          <label>О чём ваша презентация?<textarea aria-label="Тема и содержание" placeholder="Например: стратегия развития продукта на следующий год. Аудитория — команда. Добавьте цели, этапы и ожидаемые результаты." required value={brief} onChange={e => setBrief(e.target.value)} rows={5}/></label>
          <div className="vw-form-row"><label>Оформление<select aria-label="Дизайн-система новой презентации" required value={design} onChange={e => setDesign(e.target.value)}><option value="" disabled>Выберите дизайн-систему</option>{systems.map(s => <option key={s.id} value={s.id}>{s.name || s.id}</option>)}</select></label><label>Слайдов<input aria-label="Количество слайдов" type="number" min={1} max={30} required value={count} onChange={e => setCount(Number(e.target.value))}/></label></div>
          {!systems.length && <a href="#/design-systems">Добавить дизайн-систему</a>}
          <button className="vw-create" disabled={busy || !design || !brief.trim()}><Plus size={18}/>{busy ? 'Запускаем создание…' : 'Создать презентацию'}</button><small className="vw-muted">После генерации редактор откроется автоматически.</small>
        </form></div>}
        {view === 'trash' && <section className="vw-trash"><h2>Удалённые презентации</h2><p className="vw-muted">Восстановите документ, чтобы продолжить работу.</p>{!trash.length && <div className="vw-empty"><Trash2 size={36}/><h3>Корзина пуста</h3><p>Удалённые презентации появятся здесь.</p></div>}{trash.map(d => <div className="vw-trash-row" key={d.id}><FileText size={22}/><strong>{d.title}</strong><button className="button" disabled={busy} onClick={() => void manage(d.id, 'restore')}><ArchiveRestore size={16}/>Восстановить</button></div>)}</section>}
        {view === 'local' && <><div className="vw-draft-note"><FileText size={18}/><span>Это отдельный черновик в браузере. Для работы с готовой презентацией выберите её карточку слева.</span></div><VoiceEditorPage/></>}
        {view === 'deck' && (selected ? ready ? <EditPage key={selected + variant} deckId={selected} variant={variant} onVariantChange={setVariant}/> : <div className="vw-empty"><LayoutTemplate size={36}/><p role="status">{status}</p><a href={`#/decks/${selected}`}>Подробности генерации</a></div> : <div className="vw-empty"><LayoutTemplate size={40}/><h2>{loading ? 'Загрузка…' : 'Место для вашей следующей идеи'}</h2><p>Создайте презентацию, чтобы начать редактирование.</p><button className="vw-create" onClick={() => setView('new')}><Plus size={18}/>Новая презентация</button></div>)}
      </div>
    </main>
    {deleting && <div className="vw-modal-backdrop"><section className="vw-modal" role="dialog" aria-modal="true" aria-labelledby="vw-delete-title" onKeyDown={e => { if (e.key === 'Escape' && !busy) setDeleting(null); }}><Trash2 size={28}/><h2 id="vw-delete-title">Удалить презентацию?</h2><p>«{deleting.title}» переместится в корзину. Её можно восстановить.</p><div className="vw-actions"><button className="button" autoFocus disabled={busy} onClick={() => setDeleting(null)}>Оставить</button><button className="button vw-danger" disabled={busy} onClick={() => void manage(deleting.id, 'delete')}>Переместить в корзину</button></div></section></div>}
  </div>;
}
