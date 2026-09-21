import React,{useEffect,useMemo,useState} from 'react';
import {Upload,Play,Wrench,X,ClipboardList,Download,Layers} from 'lucide-react';
import type {PageProps} from '../router';
import SlideFrame,{findingIcon,findingTitle} from './SlideFrame';
import {
 DeckEvent,DeckStateResponse,DesignSystem,RunManifest,
 absoluteUrl,assetUrl,createDeck,fileUrl,fixFindings,getDeckState,getManifest,getRunManifest,
 listDesignSystems,uploadDesignSystem,watchDeckEvents,
} from './api';
import './deck.css';

// Обоснование оси различий вариантов хранится только в коде сервиса.
// RunManifest его не отдаёт, хотя store.save_run пишет "axis" в run.json,
// поэтому фразы ниже дословно повторяют designer/layout/variants.py:VARIANT_AXES,
// до появления поля в контракте.
const VARIANT_AXES: Record<string,string> = {
 a: 'как в шаблоне: план как есть, паттерн подбирается по точному числу блоков',
 b: 'плотнее: соседние слайды с одной мыслью сведены в один, карточек на слайде больше',
 c: 'данные вперёд: числа становятся крупной цифрой, диаграммой или таблицей раньше текста',
};

const STEP_LABEL: Record<string,string> = {
 plan: 'План', audit: 'Проверка правил', 'export-pptx': 'Сборка pptx', 'export-html': 'Сборка html',
 convert: 'Рендер картинок', 'convert-failed': 'Рендер недоступен', 'audit-contextual': 'Проверка по смыслу',
 done: 'Готово',
};
function stepLabel(e: DeckEvent): string {
 if (e.step === 'slide') return `Слайд ${(e.slide_index ?? 0) + 1}`;
 if (e.step === 'slide-fallback') return `Слайд ${(e.slide_index ?? 0) + 1} · запасной паттерн`;
 return STEP_LABEL[e.step] ?? e.step;
}

const FORMATS = ['pptx', 'html', 'pdf'] as const;

export default function DeckPage(_: PageProps) {
 const [dsIds, setDsIds] = useState<string[]>([]);
 const [dsId, setDsId] = useState<string | null>(null);
 const [ds, setDs] = useState<DesignSystem | null>(null);
 const [pickerOpen, setPickerOpen] = useState(false);
 const [uploadBusy, setUploadBusy] = useState(false);

 const [brief, setBrief] = useState('');
 const [purpose, setPurpose] = useState('');
 const [audience, setAudience] = useState('');
 const [slideCount, setSlideCount] = useState('');
 const [starting, setStarting] = useState(false);

 // Последняя колода переживает перезагрузку страницы: сборка идёт минуты, терять её из-за F5 нельзя.
 const [deckId, setDeckId] = useState<string | null>(() => { try { return localStorage.getItem('designer.deckId'); } catch { return null; } });
 const [deckState, setDeckState] = useState<DeckStateResponse | null>(null);
 const [events, setEvents] = useState<DeckEvent[]>([]);
 const [variant, setVariant] = useState('a');
 const [activeSlideId, setActiveSlideId] = useState<string | null>(null);
 const [activeFindingId, setActiveFindingId] = useState<string | null>(null);

 const [dismissed, setDismissed] = useState<Set<string>>(new Set());
 const [toFix, setToFix] = useState<Set<string>>(new Set());
 const [report, setReport] = useState<Record<string,{status:string;what:string}>>({});
 const [fixBusy, setFixBusy] = useState(false);

 const [runManifest, setRunManifest] = useState<RunManifest | null>(null);
 const [showRun, setShowRun] = useState(false);
 const [error, setError] = useState('');

 useEffect(() => {
  listDesignSystems().then(ids => { setDsIds(ids); if (ids.length) setDsId(prev => prev ?? ids[0]); }).catch(() => {});
 }, []);
 useEffect(() => {
  if (!dsId) { setDs(null); return; }
  getManifest(dsId).then(setDs).catch(e => setError(String(e)));
 }, [dsId]);

 useEffect(() => {
  if (!deckId) return;
  try { localStorage.setItem('designer.deckId', deckId); } catch { /* хранилище недоступно */ }
  getDeckState(deckId).then(setDeckState).catch(() => {
   try { localStorage.removeItem('designer.deckId'); } catch { /* хранилище недоступно */ }
   setDeckId(null);
  });
  const seen = new Set<string>();
  const source = watchDeckEvents(deckId, e => {
   const key = `${e.variant}-${e.step}-${e.slide_index}-${e.at}`;
   if (seen.has(key)) return;
   seen.add(key);
   setEvents(prev => [...prev, e]);
   getDeckState(deckId).then(setDeckState).catch(() => {});
   if (e.step === 'done') source.close();
  });
  return () => source.close();
 }, [deckId]);

 const variantCodes = useMemo(() => {
  const codes = Object.keys(deckState?.variants ?? {});
  return codes.length ? codes.sort() : ['a', 'b', 'c'];
 }, [deckState]);
 const activeVariant = deckState?.variants[variant];
 const scenes = activeVariant?.scenes ?? [];
 const findings = (activeVariant?.findings ?? []).filter(f => !dismissed.has(f.id));

 useEffect(() => {
  if (scenes.length && !scenes.some(s => s.slide_id === activeSlideId)) setActiveSlideId(scenes[0].slide_id);
 }, [scenes, activeSlideId]);

 const activeIndex = scenes.findIndex(s => s.slide_id === activeSlideId);
 const activeScene = activeIndex >= 0 ? scenes[activeIndex] : undefined;
 const activeImage = activeIndex >= 0 ? activeVariant?.slide_images?.[activeIndex] : undefined;
 const slideFindings = findings.filter(f => f.slide_id === activeScene?.slide_id);
 const findingsBySlide = useMemo(() => {
  const map = new Map<string, number>();
  for (const f of findings) map.set(f.slide_id, (map.get(f.slide_id) ?? 0) + 1);
  return map;
 }, [findings]);

 const ratio = ds ? ds.slide_size_emu[0] / ds.slide_size_emu[1] : 16 / 9;
 const titlePattern = ds?.patterns.find(p => p.kind === 'title');
 const titleAsset = titlePattern?.background_asset
  ? ds?.assets.find(a => a.id === titlePattern.background_asset) : undefined;

 async function upload(file: File) {
  setUploadBusy(true); setError('');
  try {
   const next = await uploadDesignSystem(file);
   setDsIds(v => Array.from(new Set([...v, next.id])));
   setDsId(next.id); setPickerOpen(false);
  } catch (e) { setError(String(e)); }
  finally { setUploadBusy(false); }
 }

 async function start() {
  if (!dsId || !brief.trim()) return;
  setStarting(true); setError('');
  try {
   const count = slideCount.trim() ? Number(slideCount) : null;
   const { deck_id } = await createDeck({
    design_system_id: dsId, brief, purpose, audience, slide_count: count, variants: ['a', 'b', 'c'],
   });
   setDeckId(deck_id); setDeckState(null); setEvents([]);
   setActiveSlideId(null); setActiveFindingId(null);
   setDismissed(new Set()); setToFix(new Set()); setReport({}); setRunManifest(null); setShowRun(false);
  } catch (e) { setError(String(e)); }
  finally { setStarting(false); }
 }

 function toggleFix(id: string) {
  setToFix(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
 }
 function dismiss(id: string) {
  setDismissed(prev => new Set(prev).add(id));
  setToFix(prev => { if (!prev.has(id)) return prev; const next = new Set(prev); next.delete(id); return next; });
 }
 async function runFix() {
  if (!deckId || !toFix.size) return;
  setFixBusy(true); setError('');
  try {
   const ids = Array.from(toFix);
   const res = await fixFindings(deckId, variant, ids);
   // Починка пересобирает сцены и файлы на сервере, но не отдаёт их в ответе:
   // забираем свежее состояние целиком, чтобы слайд на экране обновился.
   const fresh = await getDeckState(deckId);
   setDeckState(fresh);
   const next: Record<string,{status:string;what:string}> = {};
   for (const r of res.report) next[r.finding_id] = { status: r.status, what: r.what };
   setReport(next); setToFix(new Set());
  } catch (e) { setError(String(e)); }
  finally { setFixBusy(false); }
 }
 function openRun() {
  if (!runManifest && deckId) getRunManifest(deckId).then(setRunManifest).catch(e => setError(String(e)));
  setShowRun(v => !v);
 }

 const done = activeVariant?.status === 'done';
 // Упавшая сборка показывается словами сервиса: без этого экран вечно стоит на шаге «План».
 const failure = activeVariant?.status === 'error' ? (activeVariant.error || 'Сборка не удалась') : '';
 useEffect(() => { if (failure) setError(failure); }, [failure]);
 const stepsForVariant = events.filter(e => e.variant === null || e.variant === variant);

 return <div className="deck-shell">
  {deckId && <div className="deck-header">
   {FORMATS.map(fmt => <a key={fmt} className={`button outline small ${done ? '' : 'disabled'}`}
    href={done ? fileUrl(deckId, variant, `deck.${fmt}`) : undefined} download={done || undefined}
    title={`Скачать ${fmt} варианта ${variant.toUpperCase()}`} aria-label={`Скачать ${fmt}`}
    onClick={e => { if (!done) e.preventDefault(); }}><Download size={13}/>{fmt.toUpperCase()}</a>)}
   <button type="button" className="button icon" title="Карточка прогона: модель, скиллы, время шагов"
    aria-label="Прогон" onClick={openRun}><ClipboardList size={16}/></button>
   {showRun && <div className="run-panel">
    {runManifest ? <>
     <div className="run-rows"><div><span>Модель</span><span>{runManifest.model}</span></div>
      <div><span>Запуск</span><span>{runManifest.started_at}</span></div></div>
     <h3>Скиллы</h3>
     <div className="run-rows">{runManifest.skills.map(s =>
      <div key={s.name}><span>{s.name}</span><span>{s.version}</span></div>)}</div>
     <h3>Время шагов</h3>
     <div className="run-rows">{Object.entries(runManifest.timings_ms).map(([k, v]) =>
      <div key={k}><span>{k}</span><span>{v} мс</span></div>)}</div>
    </> : <p>Загрузка…</p>}
   </div>}
  </div>}
  {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}

  <div className="deck-page">
   <aside className="deck-rail">
    <div>
     <label>Шаблон</label>
     {pickerOpen ? <div className="template-pick-list">
      {dsIds.map(id => <button key={id} type="button" className={id === dsId ? 'active' : ''}
       onClick={() => { setDsId(id); setPickerOpen(false); }}>{id}</button>)}
      <label className="button outline small upload-inline">
       <Upload size={13}/>Загрузить
       <input type="file" accept=".pptx" hidden disabled={uploadBusy}
        onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ''; }}/>
      </label>
     </div> : <button type="button" className="template-pick" onClick={() => setPickerOpen(true)} title="Сменить шаблон">
      <span className="thumb">{titleAsset ? <img src={assetUrl(dsId!, titleAsset.path)} alt=""/> : <Layers size={16}/>}</span>
      <span><strong>{dsId ?? 'Не выбран'}</strong><span>Сменить</span></span>
     </button>}
    </div>
    <div><label htmlFor="brief">Бриф</label>
     <textarea id="brief" value={brief} onChange={e => setBrief(e.target.value)} placeholder="О чём презентация, для кого и зачем"/></div>
    <div><label htmlFor="purpose">Назначение</label>
     <input id="purpose" value={purpose} onChange={e => setPurpose(e.target.value)} placeholder="Питч, отчёт, обучение"/></div>
    <div><label htmlFor="audience">Аудитория</label>
     <input id="audience" value={audience} onChange={e => setAudience(e.target.value)} placeholder="Кто в зале"/></div>
    <div><label htmlFor="slide-count">Слайдов</label>
     <input id="slide-count" type="number" min={1} max={40} value={slideCount}
      onChange={e => setSlideCount(e.target.value)} placeholder="Авто"/></div>
    <button className="button primary" disabled={!dsId || !brief.trim() || starting} onClick={start}>
     <Play size={15}/>Собрать
    </button>
   </aside>

   <main className="deck-main">
    {!deckId && <div className="empty-state">
     <h2>{dsId ? 'Опишите бриф и нажмите «Собрать»' : 'Сначала загрузите или выберите шаблон'}</h2>
    </div>}
    {deckId && <>
     <div className="variant-tabs">
      {variantCodes.map(code => <button key={code} type="button" className={code === variant ? 'active' : ''}
       title={VARIANT_AXES[code] ?? ''} onClick={() => { setVariant(code); setActiveFindingId(null); }}>
       {code.toUpperCase()}</button>)}
     </div>
     {activeScene ? <SlideFrame imageUrl={activeImage ? absoluteUrl(activeImage) : null} scene={activeScene}
       ratio={ratio} findings={slideFindings} activeFindingId={activeFindingId}
       onSelectFinding={id => setActiveFindingId(id)}/>
      : <ol className="steps">
       {stepsForVariant.length ? stepsForVariant.map((e, i) =>
        <li key={i} className={i === stepsForVariant.length - 1 ? 'current' : ''}>{stepLabel(e)}</li>)
        : <li className="current">Готовим план</li>}
      </ol>}
     {scenes.length > 0 && <div className="thumb-strip">
      {scenes.map((s, i) => <button key={s.slide_id} type="button" className={s.slide_id === activeSlideId ? 'active' : ''}
       onClick={() => { setActiveSlideId(s.slide_id); setActiveFindingId(null); }}>
       <SlideFrame imageUrl={activeVariant?.slide_images?.[i] ? absoluteUrl(activeVariant.slide_images[i]) : null}
        scene={s} ratio={ratio} compact/>
       {findingsBySlide.get(s.slide_id) ? <span className="thumb-badge">{findingsBySlide.get(s.slide_id)}</span> : null}
      </button>)}
     </div>}
    </>}
   </main>

   <aside className="deck-findings">
    <h2>Находки{activeScene ? ` · слайд ${activeIndex + 1}` : ''}</h2>
    {Object.keys(report).length > 0 && <div className="finding-report-summary">
     {Object.values(report).map((r, i) => <div key={i} className={r.status}>{r.what}</div>)}
     <button type="button" onClick={() => setReport({})}>Скрыть отчёт</button>
    </div>}
    {!slideFindings.length && <p className="pane-subtitle">Огрехов не найдено</p>}
    {slideFindings.map(f => <div key={f.id} className={`finding-row ${f.severity}`}>
     <div className="finding-top">
      <input type="checkbox" checked={toFix.has(f.id)} onChange={() => toggleFix(f.id)} disabled={!f.fixable}
       title={f.fixable ? 'Отметить к исправлению' : 'Автоматической починки нет'} aria-label="Отметить к исправлению"/>
      <span title={findingTitle(f.kind)} aria-hidden="true">{findingIcon(f.kind)}</span>
      <p>{f.message}</p>
     </div>
     <div className="finding-actions">
      <button type="button" onClick={() => dismiss(f.id)} title="Скрыть находку из списка"><X size={12}/>Отклонить</button>
     </div>
    </div>)}
    <button className="button primary small" disabled={!toFix.size || fixBusy} onClick={runFix}>
     <Wrench size={13}/>Исправить{toFix.size ? ` (${toFix.size})` : ''}
    </button>
   </aside>
  </div>
 </div>;
}
