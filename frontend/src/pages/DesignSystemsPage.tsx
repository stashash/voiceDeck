import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Upload, Presentation, MonitorPlay, RotateCw, Trash2, X } from 'lucide-react';
import {
  DesignSystem, DesignSystemListItem, Pattern,
  absoluteUrl, deleteDesignSystem, describeDesignSystem, getManifest, listDesignSystemItems,
  patchDesignSystem, patternPreviewUrl, uploadDesignSystem,
} from '../designer/api';

const ROLE_LABEL: Record<string, string> = {
  background: 'Фон', surface: 'Подложка', text: 'Текст', text_muted: 'Второстепенный текст',
  accent: 'Акцент', accent_alt: 'Второй акцент',
};
const ROLE_ORDER = ['background', 'surface', 'text', 'text_muted', 'accent', 'accent_alt'];
const SCALE_ROLE: Record<string, string> = { display: 'Титул', title: 'Заголовок', heading: 'Подзаголовок', body: 'Текст', caption: 'Подпись' };
const EMBED_LABEL: Record<string, string> = {
  extracted: 'встроен, извлечён', embedded_not_extracted: 'встроен, сервис не извлёк', missing: 'в файле нет',
};
type Filter = 'all' | 'used' | 'removed';

function inUse(ds: DesignSystem, p: Pattern): boolean {
  const override = ds.pattern_overrides?.[p.id];
  return override !== undefined ? override : !p.needs_images;
}

function DsList({ items, activeId }: { items: DesignSystemListItem[]; activeId?: string }) {
  return <aside className="ds-list">
    <a className="ds-list-create" href="#/design-systems/new"><Upload size={16} strokeWidth={1.5}/>Создать</a>
    {items.map(d => <a key={d.id} className={`ds-list-item ${d.id === activeId ? 'active' : ''}`} href={`#/design-systems/${d.id}`}>
      {d.preview ? <img className="ds-list-thumb" src={absoluteUrl(d.preview)} alt=""/> : <div className="ds-list-thumb"/>}
      <span><span className="ds-list-name">{d.name}</span><br/><span className="ds-list-meta">{d.patterns} образцов</span></span>
    </a>)}
  </aside>;
}

function NewSystem({ onUploaded }: { onUploaded: (id: string) => void }) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [badName, setBadName] = useState('');
  const [error, setError] = useState('');

  const submit = useCallback(async (file: File) => {
    setBusy(true); setError(''); setBadName('');
    try { const ds = await uploadDesignSystem(file); onUploaded(ds.id); }
    catch (e) { setBadName(file.name); setError(String(e)); }
    finally { setBusy(false); }
  }, [onUploaded]);

  return <div className="ds-new-page">
    <h1 style={{ fontSize: 20 }}>Новая дизайн-система</h1>
    {error ? <div className="ds-dropzone">
      <p className="ds-error-title">«{badName}» {error.includes('не pptx') ? 'не pptx.' : 'не открылся.'}</p>
      <p>{error}</p>
      <label className="button primary">
        <Upload size={16} strokeWidth={1.5}/>Выбрать другой файл
        <input type="file" accept=".pptx" hidden disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void submit(f); e.target.value = ''; }}/>
      </label>
    </div> : <div className={`ds-dropzone ${drag ? 'drag' : ''}`}
      onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) void submit(f); }}>
      <Upload size={28} strokeWidth={1.5}/>
      <p>Перетащите pptx сюда</p>
      <label className="button primary">
        Выбрать файл
        <input type="file" accept=".pptx" hidden disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void submit(f); e.target.value = ''; }}/>
      </label>
      <p>Сервис возьмёт из pptx палитру, шрифты, кегли, поля и слайды-образцы. Сам файл не меняется.</p>
    </div>}
  </div>;
}

function Detail({ id }: { id: string }) {
  const [ds, setDs] = useState<DesignSystem | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [sample, setSample] = useState<Pattern | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { getManifest(id).then(setDs).catch(e => setError(String(e))); }, [id]);
  useEffect(() => { setDs(null); setSample(null); load(); }, [id, load]);
  useEffect(() => {
    if (!ds || ds.describe?.status !== 'running') return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [ds, load]);

  if (error) return <div className="ds-page"><p className="notice" role="alert">{error}</p></div>;
  if (!ds) return <div className="ds-page"><p className="page-loading">Загрузка</p></div>;

  const running = ds.describe?.status === 'running';
  const failed = ds.describe?.status === 'failed';
  const colorByRole = new Map(ds.tokens.colors.map(c => [c.role, c] as const));
  const removedCount = ds.patterns.filter(p => !inUse(ds, p)).length;
  const usedCount = ds.patterns.length - removedCount;
  const showRemovedBanner = removedCount > 0 && !ds.removal_confirmed && !running;
  const ratio = `${Math.round(ds.slide_size_emu[0] / ds.slide_size_emu[1] * 9)}:9`;
  const visiblePatterns = ds.patterns.filter(p => filter === 'all' || (filter === 'used') === inUse(ds, p));

  function togglePattern(p: Pattern) {
    const next = { ...(ds!.pattern_overrides ?? {}) };
    next[p.id] = !inUse(ds!, p);
    setBusy(true);
    patchDesignSystem(id, { pattern_overrides: next }).then(setDs).catch(e => setError(String(e))).finally(() => setBusy(false));
  }

  return <div className="ds-page">
    <div className="ds-header">
      <div>
        {renaming
          ? <input className="ds-name-input" autoFocus value={nameDraft} onChange={e => setNameDraft(e.target.value)}
            onBlur={() => { setRenaming(false); if (nameDraft.trim() && nameDraft !== ds.name) patchDesignSystem(id, { name: nameDraft }).then(setDs); }}
            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}/>
          : <h1 className="ds-name" onClick={() => { setNameDraft(ds.name ?? ''); setRenaming(true); }}>{ds.name || ds.id}</h1>}
        <div className="ds-meta">
          <span>Файл <b>{ds.source_file}</b></span>
          <span>Размер слайда <b>{ratio}</b></span>
        </div>
      </div>
      <div className="ds-header-actions">
        <a className="button-icon" href="#/" aria-label="Создать презентацию" title="Создать презентацию"><Presentation size={20} strokeWidth={1.5}/></a>
        <a className="button-icon" href="#/live" aria-label="Выступить" title="Выступить"><MonitorPlay size={20} strokeWidth={1.5}/></a>
        <button className="button-icon" aria-label="Удалить" title="Удалить"
          onClick={() => { if (window.confirm('Удалить дизайн-систему?')) deleteDesignSystem(id).then(() => { window.location.hash = '#/design-systems'; }); }}>
          <Trash2 size={20} strokeWidth={1.5}/>
        </button>
      </div>
    </div>

    {running && <div className="ds-status-line" role="status"><RotateCw size={18} strokeWidth={1.5} className="spin"/>
      <span>Модель описывает образцы: {ds.describe?.done ?? 0} из {ds.describe?.total ?? ds.patterns.length}</span></div>}
    {failed && <div className="ds-status-line" role="alert">
      <span>{ds.name || ds.source_file} не ответила, образцы без описания. Палитра, шрифт, кегли и поля готовы.
        Какие образцы держатся на фото, не проверено, поэтому все пока в вёрстке.</span>
      <button type="button" className="button small" onClick={() => describeDesignSystem(id).then(setDs)}>Описать заново</button>
    </div>}

    <section>
      <h2 className="ds-section-title">Палитра</h2>
      <div className="ds-palette">
        {ROLE_ORDER.map(role => {
          const c = colorByRole.get(role);
          if (!c) return null;
          return <div key={role} className="ds-swatch">
            <div className="ds-swatch-color" style={{ background: `#${c.hex.replace('#', '')}` }}/>
            <span className="ds-swatch-role">{ROLE_LABEL[role]}</span>
            <span className="ds-swatch-code">#{c.hex.replace('#', '').toUpperCase()}</span>
          </div>;
        })}
        {ds.tokens.colors.length > ROLE_ORDER.length && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Ещё {ds.tokens.colors.length - ROLE_ORDER.length} цветов</span>}
      </div>
    </section>

    <section>
      <h2 className="ds-section-title">Шрифты</h2>
      <div className="ds-fonts">
        {ds.tokens.fonts.map((f, i) => <div key={i} className="ds-font-row">
          <span className="ds-font-name">{f.family}</span>
          <span className="ds-font-role">{f.role}, {f.share}%</span>
          <span className={`ds-font-state ${f.embedded_state && f.embedded_state !== 'extracted' ? 'warn' : ''}`}>
            {EMBED_LABEL[f.embedded_state ?? 'extracted']}
          </span>
        </div>)}
      </div>
    </section>

    <section>
      <h2 className="ds-section-title">Кегли, пт</h2>
      <div className="ds-scale">
        {ds.tokens.type_scale.map((s, i) => <div key={i} className="ds-scale-row">
          <span className="ds-scale-size">{s.size_pt}</span>
          <span className="ds-scale-role">{SCALE_ROLE[s.role] ?? s.role}</span>
          <span style={{ fontSize: Math.min(s.size_pt, 28) }}>Итоги года</span>
        </div>)}
      </div>
    </section>

    <section>
      <h2 className="ds-section-title">Поля слайда</h2>
      <div className="ds-margins">
        <div className="ds-margins-inner" style={{
          left: `${ds.tokens.margins.left * 100}%`, top: `${ds.tokens.margins.top * 100}%`,
          right: `${ds.tokens.margins.right * 100}%`, bottom: `${ds.tokens.margins.bottom * 100}%`,
        }}/>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>доли ширины и высоты слайда</p>
    </section>

    <section>
      <div className="ds-patterns-toolbar">
        <h2 className="ds-section-title" style={{ marginBottom: 0 }}>Образцы</h2>
        <div className="ds-patterns-filter">
          <button type="button" className={`ds-filter-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>Все {ds.patterns.length}</button>
          <button type="button" className={`ds-filter-btn ${filter === 'used' ? 'active' : ''}`} onClick={() => setFilter('used')}>В вёрстке {usedCount}</button>
          <button type="button" className={`ds-filter-btn ${filter === 'removed' ? 'active' : ''}`} onClick={() => setFilter('removed')}>Убраны {removedCount}</button>
        </div>
      </div>
      {showRemovedBanner && <div className="ds-removed-banner">
        <span>Модель убрала из вёрстки образцы, которые без фото не работают: своих фото у сервиса нет. Флажок у образца вернёт его.</span>
        <button type="button" className="button small" onClick={() => patchDesignSystem(id, { removal_confirmed: true }).then(setDs)}>Согласен</button>
      </div>}
      <div className="ds-patterns-grid">
        {visiblePatterns.map(p => {
          const used = inUse(ds, p);
          const waiting = running && !p.purpose;
          return <div key={p.id} className="ds-pattern-card">
            <div className="ds-pattern-thumb-wrap">
              {waiting ? <div className="ds-pattern-waiting">ждёт описания</div>
                : <button type="button" style={{ padding: 0, border: 0, background: 'none', cursor: 'pointer' }} onClick={() => setSample(p)}>
                  <img className={`ds-pattern-thumb ${used ? '' : 'removed'}`}
                    src={p.preview ? patternPreviewUrl(id, p.id) : ''} alt=""/>
                </button>}
              <input type="checkbox" className="ds-pattern-check" checked={used} disabled={busy || waiting}
                aria-label={`В вёрстке: ${p.kind}`} onChange={() => togglePattern(p)}/>
            </div>
            <span className="ds-pattern-kind">{p.kind}</span>
            {!used && !waiting && <span className="ds-pattern-tag">убран моделью</span>}
          </div>;
        })}
      </div>
    </section>

    {sample && <div className="ds-sample-overlay" role="dialog" aria-label={`Образец: ${sample.kind}`} onClick={() => setSample(null)}>
      <div className="ds-sample-panel" onClick={e => e.stopPropagation()}>
        <div className="ds-sample-head"><h2>{sample.kind}</h2>
          <button type="button" className="button-icon" aria-label="Закрыть" onClick={() => setSample(null)}><X size={20} strokeWidth={1.5}/></button>
        </div>
        {sample.preview && <img className="ds-sample-img" src={patternPreviewUrl(id, sample.id)} alt=""/>}
        <div className="ds-sample-meta">
          <span>{sample.purpose || 'Назначение не описано'}</span>
          <span style={{ color: 'var(--text-muted)' }}>{inUse(ds, sample) ? 'В вёрстке' : 'Не используется'}</span>
        </div>
      </div>
    </div>}
  </div>;
}

export default function DesignSystemsPage({ id }: { id?: string }) {
  const [items, setItems] = useState<DesignSystemListItem[]>([]);
  useEffect(() => { listDesignSystemItems().then(setItems).catch(() => {}); }, [id]);

  const effectiveId = useMemo(() => id && id !== 'new' ? id : undefined, [id]);

  if (id === 'new') return <div className="ds-layout"><DsList items={items}/>
    <NewSystem onUploaded={newId => { window.location.hash = `#/design-systems/${newId}`; }}/></div>;

  if (!items.length && !effectiveId) return <div className="ds-empty-page">
    <h1>Дизайн-систем пока нет</h1>
    <a className="button primary" href="#/design-systems/new"><Upload size={16} strokeWidth={1.5}/>Создать из pptx</a>
  </div>;

  const targetId = effectiveId ?? items[0]?.id;
  if (!targetId) return <div className="ds-layout"><DsList items={items}/></div>;

  return <div className="ds-layout">
    <DsList items={items} activeId={targetId}/>
    <Detail key={targetId} id={targetId}/>
  </div>;
}
