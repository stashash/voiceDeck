import React, { useEffect, useMemo, useState } from 'react';
import { Pencil, Undo2, Copy, Trash2, Plus, Download, Send, AlertTriangle } from 'lucide-react';
import {
  DeckStateResponse, Finding, SlidePatternOption, absoluteUrl, askSlide, fileUrl, fixFindings, getDeckState,
  getSlidePatterns, patchNotes, patchSlideText, renameDeck, revertVariant, rewriteFinding, setSlidePattern, slidesAction,
} from '../designer/api';

const ASK_CHIPS = ['Короче', 'Сделай диаграммой', 'Вынести вывод в заголовок'];
const FORMATS: { ext: string; label: string }[] = [
  { ext: 'pptx', label: 'для правки в PowerPoint' },
  { ext: 'pdf', label: 'для рассылки' },
  { ext: 'html', label: 'для показа в браузере' },
];

export default function EditPage({ deckId, variant }: { deckId: string; variant: string }) {
  const [state, setState] = useState<DeckStateResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [activeEl, setActiveEl] = useState<string | null>(null);
  const [editingEl, setEditingEl] = useState<string | null>(null);
  const [draftText, setDraftText] = useState('');
  const [ask, setAsk] = useState('');
  const [notesDraft, setNotesDraft] = useState('');
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [error, setError] = useState('');

  useEffect(() => { getDeckState(deckId).then(setState).catch(e => setError(String(e))); }, [deckId]);

  const active = state?.variants[variant];
  const scenes = useMemo(() => active?.scenes ?? [], [active]);
  const scene = scenes[index];
  const deckTitle = active?.plan?.title ?? state?.plan?.title ?? '';
  const image = active?.slide_images?.[index];
  const findingsBySlide = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of active?.findings ?? []) map.set(f.slide_id, [...(map.get(f.slide_id) ?? []), f]);
    return map;
  }, [active]);
  const sceneFindings = scene ? findingsBySlide.get(scene.slide_id) ?? [] : [];
  const [patterns, setPatterns] = useState<SlidePatternOption[]>([]);

  const planNotes = active?.plan?.slides[index]?.notes ?? '';
  useEffect(() => { setNotesDraft(planNotes); setActiveEl(null); setEditingEl(null); }, [scene?.slide_id, planNotes]);
  useEffect(() => {
    if (!scene) return;
    getSlidePatterns(deckId, variant, index + 1).then(setPatterns).catch(() => setPatterns([]));
  }, [deckId, variant, index, scene?.pattern_id]);

  async function refresh() { try { setState(await getDeckState(deckId)); } catch (e) { setError(String(e)); } }
  async function guard(fn: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await fn(); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  if (!scene) return <div className="edit-shell"><div className="page-loading">{error || 'Загрузка'}</div></div>;

  return <div className="edit-shell">
    <div className="edit-topbar">
      <div className="edit-title-row">
        {renaming ? <input className="edit-title-input" aria-label="Название презентации" autoFocus value={titleDraft}
          onChange={e => setTitleDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Escape') setRenaming(false); if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          onBlur={() => { setRenaming(false); const t = titleDraft.trim(); if (t && t !== deckTitle) void guard(() => renameDeck(deckId, t)); }}/>
          : <h1 className="edit-title">{deckTitle}</h1>}
        <button type="button" className="button-icon" aria-label="Переименовать" title="Переименовать"
          onClick={() => { setTitleDraft(deckTitle); setRenaming(true); }}><Pencil size={20} strokeWidth={1.5}/></button>
      </div>
      <div role="group" aria-label="Варианты вёрстки" className="edit-variants">
        {['a', 'b', 'c'].map(v => {
          const has = state?.variants[v]?.status === 'done';
          return <a key={v} className={`edit-variant-tab ${v === variant ? 'active' : ''}`}
            href={`#/decks/${deckId}/edit/${v}`} aria-current={v === variant ? 'page' : undefined}
            title={v === 'a' || !has ? undefined : 'Проверки смысла у этого варианта не было'}>
            Вариант {v === 'a' ? 1 : v === 'b' ? 2 : 3}
          </a>;
        })}
      </div>
      <div style={{ display: 'flex', gap: 8, position: 'relative' }}>
        <button type="button" className="button primary" aria-label="Скачать: pptx, pdf или html" onClick={() => setDownloadOpen(v => !v)}>
          <Download size={18} strokeWidth={1.5}/>Скачать
        </button>
        {downloadOpen && <ul role="menu" aria-label="Формат файла" className="download-menu">
          {FORMATS.map(f => <li key={f.ext} role="menuitem" tabIndex={0}>
            <a className="download-item" href={fileUrl(deckId, variant, `deck.${f.ext}`)} download onClick={() => setDownloadOpen(false)}>
              <span className="download-item-ext">{f.ext}</span><span className="download-item-sub">{f.label}</span>
            </a>
          </li>)}
        </ul>}
      </div>
    </div>
    {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
    <div className="edit-body">
      <aside className="edit-rail" aria-label="Слайды">
        {scenes.map((s, i) => {
          const fs = findingsBySlide.get(s.slide_id) ?? [];
          const hasError = fs.some(f => f.severity === 'error');
          return <a key={s.slide_id} className={`edit-thumb-row ${i === index ? 'current' : ''}`}
            aria-label={`Слайд ${i + 1}`} aria-current={i === index ? 'true' : undefined}
            href={`#slide-${i + 1}`} onClick={e => { e.preventDefault(); setIndex(i); }}>
            <span className="edit-thumb-num">{i + 1}</span>
            <span className="edit-thumb-wrap">
              {active?.slide_images?.[i] ? <img className="edit-thumb" src={absoluteUrl(active.slide_images[i])} alt=""/> : <div className="edit-thumb"/>}
              {fs.length > 0 && <span className={`edit-thumb-badge ${hasError ? 'error' : ''}`}>
                {hasError && <AlertTriangle size={12} strokeWidth={1.5}/>}{fs.length}
              </span>}
            </span>
          </a>;
        })}
        <button type="button" className="edit-add-slide" disabled={busy}
          onClick={() => guard(() => slidesAction(deckId, variant, { action: 'add', index }))}>
          <Plus size={16} strokeWidth={1.5}/>Слайд
        </button>
      </aside>
      <div className="edit-canvas">
        <div className="edit-slide-stage">
          {image ? <img className="edit-slide-img" src={absoluteUrl(image)} alt=""/> : <div className="edit-slide-img"/>}
          {scene.elements.filter(el => el.type === 'text').map(el => {
            const [x, y, w, h] = el.box;
            const style: React.CSSProperties = { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` };
            return <div key={el.id} className={`edit-el-box ${activeEl === el.id ? 'active' : ''}`} style={style}
              onClick={() => setActiveEl(el.id)}>
              {activeEl === el.id && editingEl !== el.id && <div className="edit-el-toolbar" role="toolbar" aria-label="Текст на слайде"
                style={{ left: 0, top: '100%', marginTop: 4 }}>
                <button type="button" className="button-icon" aria-label="Править текст" title="Править текст"
                  onClick={() => { setEditingEl(el.id); setDraftText(el.text); }}><Pencil size={20} strokeWidth={1.5}/></button>
                <button type="button" className="button-icon" aria-label="Вернуть как было" title="Вернуть как было" disabled={busy}
                  onClick={() => guard(() => revertVariant(deckId, variant))}><Undo2 size={20} strokeWidth={1.5}/></button>
              </div>}
              {editingEl === el.id && <div className="edit-el-edit" style={{ position: 'absolute', left: 0, top: '100%', marginTop: 4, zIndex: 6 }}
                onClick={e => e.stopPropagation()}>
                <textarea value={draftText} onChange={e => setDraftText(e.target.value)} autoFocus/>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="button primary small" disabled={busy}
                    onClick={() => guard(() => patchSlideText(deckId, variant, index + 1, el.id, draftText)).then(() => setEditingEl(null))}>Сохранить</button>
                  <button type="button" className="button small" onClick={() => setEditingEl(null)}>Отмена</button>
                </div>
              </div>}
            </div>;
          })}
        </div>
        <div className="edit-notes">
          <label htmlFor="notes">Заметки докладчика</label>
          <textarea id="notes" rows={2} value={notesDraft} onChange={e => setNotesDraft(e.target.value)}
            onBlur={() => { if (notesDraft !== planNotes) void guard(() => patchNotes(deckId, variant, index + 1, notesDraft)); }}/>
        </div>
      </div>
      <aside className="edit-panel" aria-label={`Слайд ${index + 1}`}>
        <div className="edit-panel-head">
          <h2>Слайд {index + 1}</h2>
          <div className="edit-panel-head-actions">
            <button type="button" className="button-icon" aria-label="Копия слайда" title="Копия слайда" disabled={busy}
              onClick={() => guard(() => slidesAction(deckId, variant, { action: 'copy', index }))}><Copy size={20} strokeWidth={1.5}/></button>
            <button type="button" className="button-icon" aria-label="Удалить слайд" title="Удалить слайд" disabled={busy}
              onClick={() => guard(() => slidesAction(deckId, variant, { action: 'delete', index }))}><Trash2 size={20} strokeWidth={1.5}/></button>
          </div>
        </div>
        <div>
          <div className="panel-section-head"><h3>Образец</h3></div>
          <div className="pattern-grid">
            {patterns.map(p => <button key={p.pattern_id} type="button" className={`pattern-item ${p.current ? 'active' : ''}`}
              aria-pressed={p.current} aria-label={`Образец: ${p.kind}`} disabled={busy}
              onClick={() => !p.current && guard(() => setSlidePattern(deckId, variant, index + 1, p.pattern_id))}>
              {p.preview ? <img src={absoluteUrl(p.preview)} alt=""/> : <div style={{ width: 148, height: 83, background: 'var(--surface-2)', borderRadius: 6 }}/>}
              <span>{p.current ? `Текущий: ${p.kind}` : p.kind}</span>
            </button>)}
          </div>
        </div>
        <div className="ask-block">
          <label htmlFor="ask">Попросить агента</label>
          <div className="ask-row">
            <input id="ask" className="ask-input" type="text" value={ask} onChange={e => setAsk(e.target.value)}
              placeholder="Например: убери вводную фразу из заголовка"/>
            <button type="button" className="ask-send" aria-label="Отправить агенту" disabled={!ask.trim() || busy}
              onClick={() => guard(() => askSlide(deckId, variant, index + 1, ask)).then(() => setAsk(''))}>
              <Send size={18} strokeWidth={1.5}/>
            </button>
          </div>
          <div className="chip-row">
            {ASK_CHIPS.map(c => <button key={c} type="button" className="chip" disabled={busy}
              onClick={() => guard(() => askSlide(deckId, variant, index + 1, c))}>{c}</button>)}
          </div>
        </div>
        <div>
          <div className="panel-section-head"><h3>Замечания проверки</h3><span className="findings-count">{sceneFindings.length}</span></div>
          <ul className="findings-list">
            {sceneFindings.map(f => <li key={f.id} className="finding-item">
              <AlertTriangle size={18} strokeWidth={1.5} color={f.severity === 'error' ? 'var(--danger)' : 'var(--text-muted)'}/>
              <span className="finding-body">
                <span className={`finding-kind ${f.severity}`}>{f.severity === 'error' ? 'Ошибка' : 'Предупреждение'}</span>
                {f.message}
              </span>
              {f.fixable
                ? <button type="button" className="button small" disabled={busy}
                  onClick={() => guard(() => fixFindings(deckId, variant, [f.id]))}>Исправить</button>
                : <button type="button" className="button small" disabled={busy}
                  onClick={() => guard(() => rewriteFinding(deckId, variant, f.id))}>Переписать</button>}
            </li>)}
          </ul>
        </div>
      </aside>
    </div>
  </div>;
}
