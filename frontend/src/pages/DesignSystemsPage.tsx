import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Upload, Presentation, MonitorPlay, RotateCw, MoreHorizontal, ChevronDown, Info, AlertTriangle, ChevronLeft, ChevronRight, X, Check } from 'lucide-react';
import {
  DesignSystem, DesignSystemListItem, Pattern,
  absoluteUrl, deleteDesignSystem, describeDesignSystem, getAgentAssignments, getManifest, listAgents, listDesignSystemItems,
  patchDesignSystem, patternPreviewUrl, uploadDesignSystem,
} from '../designer/api';
import { agentDisplayName } from '../designer/agentName';
import { KIND_LABEL, plural } from '../designer/labels';

// Словарь типов образцов и подписей ролей — docs/design/canvas/gen.py (KIND, ROLE_RU, STEP_RU, FROLE).
const KIND = KIND_LABEL;
const ROLE_LABEL: Record<string, string> = {
  background: 'Фон', surface: 'Подложка', text: 'Текст', text_muted: 'Второстепенный текст',
  accent: 'Акцент', accent_alt: 'Второй акцент',
};
const ROLE_ORDER = ['background', 'surface', 'text', 'text_muted', 'accent', 'accent_alt'];
const STEP_LABEL: Record<string, string> = { display: 'Титул', title: 'Заголовок', heading: 'Подзаголовок', body: 'Текст', caption: 'Подпись' };
const FROLE: Record<string, string> = { body: 'основной текст', heading: 'заголовки', mono: 'код', other: 'прочий текст' };
const FONT_TIP: Record<string, string> = {
  extracted: 'Шрифт встроен в pptx и извлечён сервисом.',
  embedded_not_extracted: 'Шрифт лежит в pptx в сжатом виде (EOT), сервис его не достал. Установите шрифт на машине, где будете показывать, иначе текст слайдов откроется другим шрифтом',
  missing: 'Шрифта нет внутри pptx. Установите его на машине, где будете показывать, иначе текст слайдов откроется другим шрифтом',
};
const FONT_STATE_TEXT: Record<string, string> = { extracted: 'встроен, извлечён', embedded_not_extracted: 'встроен, сервис не извлёк', missing: 'в файле нет' };
const REMOVE_TIP = 'Модель убрала образец из вёрстки: без фото он не работает, в презентации осталась бы пустая рамка. Флажок вернёт его.';

type Filter = 'all' | 'used' | 'removed';

function inUse(ds: DesignSystem, p: Pattern): boolean {
  const override = ds.pattern_overrides?.[p.id];
  return override !== undefined ? override : !p.needs_images;
}
function pct(v: number): string { return `${(v * 100).toFixed(1).replace('.', ',')} %`; }

const SLOT_ROLE_LABEL: Record<string, string> = { title: 'Заголовок', heading: 'заголовок', body: 'текст', caption: 'подпись', number: 'число', label: 'метка' };
function slotBoxes(p: Pattern): { label: string; box: [number, number, number, number] }[] {
  const boxes = (p.slots ?? []).map(s => ({ label: SLOT_ROLE_LABEL[s.role] ?? s.role, box: s.box }));
  for (const g of p.groups ?? []) (g.units ?? []).forEach((u, i) => boxes.push({ label: `Карточка ${i + 1}`, box: u.box }));
  return boxes;
}
function capacity(p: Pattern): string {
  const g = p.groups?.[0];
  if (!g) return 'Места под текст отмечены на картинке';
  const what = Array.from(new Set((g.unit_slots ?? []).map(s => SLOT_ROLE_LABEL[s.role] ?? 'текст'))).join(', ') || 'текст';
  return `Заголовок слайда и карточки: от ${g.min_units} до ${g.max_units}, в каждой ${what}`;
}

function Sidebar({ items, activeId }: { items: DesignSystemListItem[]; activeId?: string }) {
  return <aside className="ds-sidebar">
    <div className="ds-sidebar-head">
      <h2>Дизайн-системы</h2>
      <a className="button-icon" href="#/design-systems/new" aria-label="Создать из pptx" title="Создать из pptx" style={{ background: 'var(--surface-2)', color: 'var(--text)' }}>
        <Upload size={18} strokeWidth={1.5}/>
      </a>
    </div>
    <div className="ds-sidebar-list">
      {items.map(d => <a key={d.id} className={`ds-side-item ${d.id === activeId ? 'active' : ''}`} href={`#/design-systems/${d.id}`}>
        {d.preview ? <img className="ds-side-thumb" src={absoluteUrl(d.preview)} alt=""/> : <div className="ds-side-thumb"/>}
        <span className="ds-side-body">
          <span className="ds-side-name">{d.name}</span>
          {d.describe_status === 'running'
            ? <span className="ds-side-meta parsing"><span className="dot"/>идёт разбор</span>
            : <span className="ds-side-meta">{plural(d.patterns, 'образец', 'образца', 'образцов')}</span>}
        </span>
      </a>)}
    </div>
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

  return <div className="ds-new-col">
    <h1>Новая дизайн-система</h1>
    {error && <div className="ds-upload-error" role="alert">
      <AlertTriangle size={20} strokeWidth={1.5} color="var(--danger)"/>
      <span><b>«{badName}» {error.includes('не pptx') ? 'не pptx.' : 'не открылся.'}</b> {error.includes('не pptx')
        ? 'Выберите презентацию PowerPoint с расширением .pptx.'
        : 'Файл повреждён или сохранён не до конца. Сохраните его в PowerPoint заново и загрузите ещё раз.'}</span>
    </div>}
    <div className={`ds-dropzone ${drag ? 'drag' : ''}`}
      onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) void submit(f); }}>
      <span className="ds-dropzone-icon"><Upload size={28} strokeWidth={1.5} color="var(--accent)"/></span>
      <span className="ds-dropzone-label">Перетащите pptx сюда</span>
      <label className="button primary">
        {error ? 'Выбрать другой файл' : 'Выбрать файл'}
        <input type="file" accept=".pptx" hidden disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void submit(f); e.target.value = ''; }}/>
      </label>
    </div>
    <p>Сервис возьмёт из pptx палитру, шрифты, кегли, поля и слайды-образцы. Сам файл не меняется.</p>
  </div>;
}

function SampleDrawer({ ds, id, patterns, onClose, onNav, onToggle }: {
  ds: DesignSystem; id: string; patterns: Pattern[]; onClose: () => void;
  onNav: (dir: -1 | 1) => void; onToggle: (p: Pattern) => void;
}) {
  const p = patterns.find(x => x.id === id);
  if (!p) return null;
  const used = inUse(ds, p);
  return <>
    <div className="ds-drawer-backdrop" onClick={onClose}/>
    <aside className="ds-drawer" role="dialog" aria-modal="true" aria-label={`Образец ${p.id}`}>
      <div className="ds-drawer-head">
        <div className="ds-drawer-title">
          <h2>{KIND[p.kind] ?? p.kind}</h2>
          <span>образец {patterns.indexOf(p) + 1} из {patterns.length}</span>
        </div>
        <div className="ds-drawer-actions">
          <button type="button" className="button-icon" aria-label="Предыдущий образец" onClick={() => onNav(-1)}><ChevronLeft size={20} strokeWidth={1.5}/></button>
          <button type="button" className="button-icon" aria-label="Следующий образец" onClick={() => onNav(1)}><ChevronRight size={20} strokeWidth={1.5}/></button>
          <button type="button" className="button-icon" aria-label="Закрыть" onClick={onClose}><X size={20} strokeWidth={1.5}/></button>
        </div>
      </div>
      {p.preview && <div className="ds-drawer-img-wrap">
        <img className="ds-drawer-img" src={patternPreviewUrl(ds.id, p.id)} alt=""/>
        {slotBoxes(p).map((b, i) => <div key={i} className="ds-slot-box"
          style={{ left: `${b.box[0] * 100}%`, top: `${b.box[1] * 100}%`, width: `${b.box[2] * 100}%`, height: `${b.box[3] * 100}%` }}>
          <span className="ds-slot-label">{b.label}</span>
        </div>)}
      </div>}
      <p className="ds-drawer-purpose">{p.purpose || 'Модель ещё не описала образец.'}</p>
      <p className="ds-drawer-capacity">{capacity(p)}</p>
      <label className="ds-drawer-checkbox">
        <input type="checkbox" checked={used} onChange={() => onToggle(p)}/>В вёрстке
      </label>
    </aside>
  </>;
}

function Detail({ id, onChanged }: { id: string; onChanged?: () => void }) {
  const [ds, setDs] = useState<DesignSystem | null>(null);
  // Имя агента, который описывает образцы: его называет полоса сбоя описания.
  const [describeAgent, setDescribeAgent] = useState('');
  useEffect(() => {
    Promise.all([getAgentAssignments(), listAgents()]).then(([assign, agents]) => {
      const a = agents.find(x => x.id === assign.describe);
      setDescribeAgent(a ? agentDisplayName(a) : '');
    }).catch(() => setDescribeAgent(''));
  }, []);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [sampleId, setSampleId] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [moreColors, setMoreColors] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const load = useCallback(() => { getManifest(id).then(setDs).catch(e => setError(String(e))); }, [id]);
  useEffect(() => { setDs(null); setSampleId(null); setMoreColors(false); load(); }, [id, load]);
  // Список слева показывает имя и «идёт разбор»: перечитывается, когда они меняются здесь.
  useEffect(() => { if (ds) onChanged?.(); }, [ds?.describe?.status, ds?.name]);
  useEffect(() => {
    if (!ds || ds.describe?.status !== 'running') return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [ds, load]);

  if (error) return <div className="ds-main"><p className="notice" role="alert">{error}</p></div>;
  if (!ds) return <div className="ds-main"><p className="page-loading">Загрузка</p></div>;

  const running = ds.describe?.status === 'running';
  const failed = ds.describe?.status === 'failed';
  // docs/model.md: цвет роли — наибольшая доля в замере слайдов (usage), тема только если в замере роли нет.
  const pickRole = (role: string) => {
    const of = (source: string) => ds.tokens.colors.filter(c => c.role === role && c.source === source);
    const pool = of('usage').length ? of('usage') : of('theme');
    return pool.reduce<typeof pool[number] | undefined>((best, c) => (!best || c.share > best.share ? c : best), undefined);
  };
  const mainColors = ROLE_ORDER.map(pickRole).filter((c): c is NonNullable<typeof c> => !!c);
  const mainHex = new Set(mainColors.map(c => c.hex));
  const restColors = ds.tokens.colors.filter((c, i, all) => !mainHex.has(c.hex) && all.findIndex(o => o.hex === c.hex) === i);
  const removedCount = ds.patterns.filter(p => !inUse(ds, p)).length;
  const usedCount = ds.patterns.length - removedCount;
  const showRemovedBanner = removedCount > 0 && !ds.removal_confirmed && !running && !failed;
  const frameW = 300, frameH = Math.round(frameW * 9 / 16);
  const m = ds.tokens.margins;
  const visiblePatterns = ds.patterns.filter(p => filter === 'all' || (filter === 'used') === inUse(ds, p));

  function togglePattern(p: Pattern) {
    const next = { ...(ds!.pattern_overrides ?? {}) };
    next[p.id] = !inUse(ds!, p);
    setBusy(true);
    patchDesignSystem(id, { pattern_overrides: next }).then(setDs).catch(e => setError(String(e))).finally(() => setBusy(false));
  }
  function nav(dir: -1 | 1) {
    const i = ds!.patterns.findIndex(p => p.id === sampleId);
    const next = ds!.patterns[(i + dir + ds!.patterns.length) % ds!.patterns.length];
    setSampleId(next.id);
  }

  return <div className="ds-main">
    <div className="ds-header">
      <div className="ds-header-left">
        <div className="ds-header-name-row">
          {renaming
            ? <input className="ds-name-input" autoFocus value={nameDraft} onChange={e => setNameDraft(e.target.value)}
              onBlur={() => { setRenaming(false); if (nameDraft.trim() && nameDraft !== ds.name) patchDesignSystem(id, { name: nameDraft }).then(setDs); }}
              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}/>
            : <h1 className="ds-name">{running ? (ds.source_file.replace(/\.pptx$/i, '').replace(/[_-]/g, ' ')) : (ds.name || ds.id)}</h1>}
          <button type="button" className="button-icon" aria-label="Переименовать" title="Переименовать" onClick={() => { setNameDraft(ds.name ?? ''); setRenaming(true); }}>
            <span style={{ fontSize: 16 }}>✎</span>
          </button>
        </div>
        <div className="ds-header-meta">
          <span className="meta-item"><span>Файл</span><span>{ds.source_file}</span></span>
          <span className="meta-item"><span>Размер слайда</span><span>16:9</span></span>
        </div>
      </div>
      <div className="ds-header-actions" style={{ opacity: running ? .45 : 1 }}>
        <a className="button primary" href={`#/?ds=${encodeURIComponent(id)}`} title={running ? 'Станет доступно, когда модель опишет образцы' : 'Собрать презентацию по брифу на этой системе'}>
          <Presentation size={18} strokeWidth={1.5}/>Создать презентацию
        </a>
        <a className="button" href={`#/live?ds=${encodeURIComponent(id)}`} title={running ? 'Станет доступно, когда модель опишет образцы' : 'Слайды из речи на этой системе'}>
          <MonitorPlay size={18} strokeWidth={1.5}/>Выступить
        </a>
        <div style={{ position: 'relative' }}>
          <button type="button" className="button-icon" aria-label="Ещё: удалить систему" title="Ещё" onClick={() => setMenuOpen(v => !v)}>
            <MoreHorizontal size={20} strokeWidth={1.5}/>
          </button>
          {menuOpen && <ul className="download-menu" role="menu" style={{ top: 40, width: 180 }}>
            <li role="menuitem" tabIndex={0}>
              <button type="button" className="download-item" onClick={() => { setMenuOpen(false); if (window.confirm('Удалить дизайн-систему?')) deleteDesignSystem(id).then(() => { window.location.hash = '#/design-systems'; }); }}>
                <span className="download-item-ext" style={{ color: 'var(--danger)' }}>Удалить</span>
              </button>
            </li>
          </ul>}
        </div>
      </div>
    </div>

    {running && <div className="ds-strip" role="status">
      <div className="ds-strip-top">
        <span className="ds-strip-ok"><Check size={16} strokeWidth={1.5} color="var(--success)"/>Палитра, шрифт, кегли, поля готовы</span>
        <span>Модель описывает образцы: {ds.describe?.done ?? 0} из {ds.describe?.total ?? ds.patterns.length}</span>
      </div>
      <div className="ds-progress" role="progressbar" aria-valuemin={0} aria-valuemax={ds.describe?.total ?? ds.patterns.length} aria-valuenow={ds.describe?.done ?? 0}>
        <div className="ds-progress-bar" style={{ width: `${((ds.describe?.done ?? 0) / (ds.describe?.total || 1)) * 100}%` }}/>
      </div>
    </div>}
    {failed && <div className="ds-error-strip" role="alert">
      <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}><AlertTriangle size={20} strokeWidth={1.5} color="var(--danger)"/>
        <span><b style={{ fontWeight: 600 }}>{describeAgent ? `Агент ${describeAgent} не ответил` : 'Модель не ответила'}, образцы без описания.</b> Палитра, шрифт, кегли и поля готовы.
          Какие образцы держатся на фото, не проверено, поэтому все пока в вёрстке. <a href="#/settings">Агенты и модели</a></span></span>
      <button type="button" className="button" onClick={() => describeDesignSystem(id).then(setDs)}><RotateCw size={18} strokeWidth={1.5}/>Описать заново</button>
    </div>}

    <div className={`ds-body ${(running || failed) ? '' : 'tight'}`}>
      <section>
        <div className="ds-section-title-row">
          <h2>Палитра</h2>
          {restColors.length > 0 && <button type="button" className="ds-more-btn" aria-expanded={moreColors} onClick={() => setMoreColors(v => !v)}>
            Ещё {restColors.length} <ChevronDown size={16} strokeWidth={1.5}/>
          </button>}
        </div>
        <div className="ds-palette-grid">
          {mainColors.map(c => <button key={c.role} type="button" className="ds-swatch" title={`Все цвета роли «${ROLE_LABEL[c.role]}»`}>
            <span className="ds-swatch-block" style={{ background: `#${c.hex.replace('#', '')}` }}/>
            <span><span className="ds-swatch-role">{ROLE_LABEL[c.role]}</span><br/>
              <span className="ds-swatch-code">#{c.hex.replace('#', '').toUpperCase()}</span></span>
          </button>)}
        </div>
        {moreColors && <div className="ds-palette-grid" style={{ marginTop: 16 }}>
          {restColors.map((c, i) => <button key={i} type="button" className="ds-swatch">
            <span className="ds-swatch-block" style={{ background: `#${c.hex.replace('#', '')}` }}/>
            <span><span className="ds-swatch-role">{c.role}</span><br/>
              <span className="ds-swatch-code">#{c.hex.replace('#', '').toUpperCase()}</span></span>
          </button>)}
        </div>}
      </section>

      <section className="ds-cards-row">
        <div className="card tight">
          <h2 className="ds-section-title-row" style={{ minHeight: 'auto' }}>{ds.tokens.fonts.length === 1 ? 'Шрифт' : 'Шрифты'}</h2>
          <div className="ds-font-preview">{ds.tokens.fonts[0]?.family}</div>
          <div className="ds-font-rows">
            {ds.tokens.fonts.map((f, i) => {
              const state = f.embedded_state ?? 'extracted';
              return <div key={i} className="ds-font-row" title={FONT_TIP[state]}>
                <div className="ds-font-row-top">
                  {ds.tokens.fonts.length > 1 ? <span className="ds-font-family">{f.family}</span> : <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Доля текста</span>}
                  <span className="ds-font-role">{FROLE[f.role] ?? f.role}, {Math.round(f.share * 100)} %</span>
                </div>
                <span className="ds-font-state"><Info size={16} strokeWidth={1.5} color="var(--text-muted)"/>{FONT_STATE_TEXT[state]}</span>
              </div>;
            })}
          </div>
        </div>
        <div className="card">
          <h2 className="ds-section-title-row" style={{ minHeight: 'auto' }}>Кегли, пт</h2>
          <div className="ds-scale-rows">
            {ds.tokens.type_scale.map((s, i, all) => <div key={i} className="ds-scale-row">
              <span className="ds-scale-size">{s.size_pt}</span>
              <span className="ds-scale-role">{s.role === 'caption' && all.slice(0, i).some(o => o.role === 'caption')
                ? 'Мелкая подпись' : STEP_LABEL[s.role] ?? s.role}</span>
              <span className="ds-scale-sample" style={{ fontSize: Math.min(s.size_pt, 30) }}>Итоги года</span>
            </div>)}
          </div>
        </div>
        <div className="card">
          <h2 className="ds-section-title-row" style={{ minHeight: 'auto' }}>Поля слайда</h2>
          <div className="ds-margins-frame" style={{ width: frameW, height: frameH }}
            role="img" aria-label={`Поля слайда: слева ${pct(m.left)}, сверху ${pct(m.top)}, справа ${pct(m.right)}, снизу ${pct(m.bottom)}`}>
            <div className="ds-margins-inner" style={{ left: m.left * frameW, top: m.top * frameH, right: m.right * frameW, bottom: m.bottom * frameH }}/>
            <span className="ds-margins-label" style={{ left: m.left * frameW + 6, top: frameH / 2 - 7 }}>{pct(m.left)}</span>
            <span className="ds-margins-label" style={{ right: m.right * frameW + 6, top: frameH / 2 - 7 }}>{pct(m.right)}</span>
            <span className="ds-margins-label" style={{ left: frameW / 2 - 20, top: m.top * frameH + 4 }}>{pct(m.top)}</span>
            <span className="ds-margins-label" style={{ left: frameW / 2 - 20, bottom: m.bottom * frameH + 4 }}>{pct(m.bottom)}</span>
          </div>
          <div className="ds-margins-caption">доли ширины и высоты слайда</div>
        </div>
      </section>

      <section>
        <div className="ds-section-title-row">
          <h2>Образцы</h2>
          {running
            ? <span className="ds-filter-hint">флажки станут доступны, когда модель опишет все образцы</span>
            : <div className="ds-filters">
              <button type="button" className={`ds-filter-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>Все {ds.patterns.length}</button>
              <button type="button" className={`ds-filter-btn ${filter === 'used' ? 'active' : ''}`} onClick={() => setFilter('used')}>В вёрстке {usedCount}</button>
              <button type="button" className={`ds-filter-btn ${filter === 'removed' ? 'active' : ''}`} onClick={() => setFilter('removed')}>Убраны {removedCount}</button>
            </div>}
        </div>
        {showRemovedBanner && <div className="ds-removed-banner" style={{ marginBottom: 16 }}>
          <span className="ds-removed-banner-text"><Info size={20} strokeWidth={1.5} color="var(--text-muted)"/>
            <span>Модель убрала из вёрстки образцы, которые без фото не работают: своих фото у сервиса нет. <span style={{ color: 'var(--text-muted)' }}>Флажок у образца вернёт его.</span></span></span>
          <button type="button" className="button" onClick={() => patchDesignSystem(id, { removal_confirmed: true }).then(setDs)}>Согласен</button>
        </div>}
        <div className="ds-patterns-grid">
          {visiblePatterns.map(p => {
            const used = inUse(ds, p);
            const waiting = running && !p.purpose;
            const kind = waiting ? 'Образец' : (KIND[p.kind] ?? p.kind);
            return <div key={p.id} className="ds-sample-cell">
              {waiting ? <div className="ds-sample-waiting">ждёт описания</div> : <button type="button" className="ds-sample-link" style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
                title={!used ? REMOVE_TIP : p.purpose} aria-label={`Образец: ${kind}. Открыть`} onClick={() => setSampleId(p.id)}>
                <span className="ds-sample-thumb-wrap">
                  {p.preview && <img className={`ds-sample-thumb ${!used ? 'removed' : ''}`} src={patternPreviewUrl(id, p.id)} alt=""/>}
                  {!used && <span className="ds-sample-tag">убран моделью</span>}
                </span>
                <span className="ds-sample-row">
                  <span className={`ds-sample-kind ${!used ? 'removed' : ''}`}>{kind}</span>
                  <span className="ds-sample-num">{p.source_slide ?? p.id}</span>
                </span>
              </button>}
              <button type="button" className="ds-sample-check" disabled={busy || waiting} aria-label={`Образец ${p.source_slide ?? p.id} в вёрстке`} onClick={() => togglePattern(p)}>
                <span className={`ds-check-mark ${used ? 'on' : ''}`}>{used && <Check size={14} strokeWidth={2} color="var(--accent-ink)"/>}</span>
              </button>
            </div>;
          })}
        </div>
      </section>
    </div>

    {sampleId && <SampleDrawer ds={ds} id={sampleId} patterns={ds.patterns} onClose={() => setSampleId(null)} onNav={nav} onToggle={togglePattern}/>}
  </div>;
}

export default function DesignSystemsPage({ id }: { id?: string }) {
  const [items, setItems] = useState<DesignSystemListItem[]>([]);
  const reloadItems = useCallback(() => { listDesignSystemItems().then(setItems).catch(() => {}); }, []);
  useEffect(() => { reloadItems(); }, [id, reloadItems]);

  const effectiveId = useMemo(() => id && id !== 'new' ? id : undefined, [id]);

  if (id === 'new') return <div className="ds-layout"><Sidebar items={items}/>
    <NewSystem onUploaded={newId => { window.location.hash = `#/design-systems/${newId}`; }}/></div>;

  if (!items.length && !effectiveId) return <div className="ds-empty-page">
    <h1>Дизайн-систем пока нет</h1>
    <a className="button primary" href="#/design-systems/new"><Upload size={16} strokeWidth={1.5}/>Создать из pptx</a>
  </div>;

  const targetId = effectiveId ?? items[0]?.id;
  if (!targetId) return <div className="ds-layout"><Sidebar items={items}/></div>;

  return <div className="ds-layout">
    <Sidebar items={items} activeId={targetId}/>
    <Detail key={targetId} id={targetId} onChanged={reloadItems}/>
  </div>;
}
