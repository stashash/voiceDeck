import React, { useEffect, useMemo, useState } from 'react';
import { plural } from '../designer/labels';
import { Check, Square, AlertTriangle, RotateCw, Settings, Boxes } from 'lucide-react';
import {
  DeckEvent, DeckStateResponse, absoluteUrl, cancelDeck, getAgentAssignments, getDeckState, getRunManifest, watchDeckEvents,
} from '../designer/api';
import { STEP_LABEL, StepView, buildSteps } from '../designer/generation';
import { modelDisplayName } from '../designer/agentName';

const VARIANTS = ['a', 'b', 'c'];

function seconds(ms: number | null): string {
  if (ms === null) return '';
  const s = ms / 1000;
  return s < 1 ? '<1 с' : `${Math.round(s)} с`;
}

function StepRow({ step, planTitles }: { step: StepView; planTitles?: string[] }) {
  const title = step.id === 'plan' && step.total ? `План: ${plural(step.total, 'слайд', 'слайда', 'слайдов')}`
    : step.id === 'layout' && step.total !== undefined ? `Вёрстка: готово ${step.doneCount ?? 0} из ${step.total}`
    : STEP_LABEL[step.id];
  return <li className="gen-step" aria-current={step.status === 'current' ? 'step' : undefined}>
    <span className={`gen-step-icon ${step.status}`}>
      {step.status === 'done' && <Check size={14} strokeWidth={1.5} color="var(--accent-ink)"/>}
      {step.status === 'error' && <AlertTriangle size={14} strokeWidth={1.5} color="var(--accent-ink)"/>}
    </span>
    <div className="gen-step-body">
      <div className="gen-step-row">
        <span className={`gen-step-title ${step.status === 'done' ? 'strong' : step.status === 'current' ? 'active' : ''}`}>{title}</span>
        {step.endAt !== null && step.startAt !== null && <span className="gen-step-time">{seconds(step.endAt - step.startAt)}</span>}
      </div>
      {step.id === 'layout' && step.status === 'current' && step.total ? <div className="gen-progress" role="progressbar"
        aria-valuemin={0} aria-valuemax={step.total} aria-valuenow={step.doneCount ?? 0} aria-label="Готово слайдов">
        <div className="gen-progress-bar" style={{ width: `${((step.doneCount ?? 0) / step.total) * 100}%` }}/>
      </div> : null}
      {step.id === 'plan' && planTitles?.length ? <ol className="gen-plan-list">
        {planTitles.map((title, i) => <li key={i}>{i + 1}. {title}</li>)}
      </ol> : null}
    </div>
  </li>;
}

export default function GenerationPage({ deckId }: { deckId: string }) {
  const [state, setState] = useState<DeckStateResponse | null>(null);
  const [events, setEvents] = useState<DeckEvent[]>([]);
  const [variant, setVariant] = useState('a');
  const [stopped, setStopped] = useState(false);
  const [error, setError] = useState('');
  // Кто генерирует: модель из run.json; пока его нет (идёт первый вариант), назначение «Презентации».
  const [agentName, setAgentName] = useState('');
  useEffect(() => {
    getRunManifest(deckId).then(run => setAgentName(modelDisplayName(run.model))).catch(() =>
      getAgentAssignments().then(a => setAgentName(modelDisplayName(a.deck))).catch(() => setAgentName('')));
  }, [deckId, state?.variants.a?.status]);

  useEffect(() => {
    setState(null); setEvents([]); setStopped(false); setError('');
    getDeckState(deckId).then(setState).catch(e => setError(String(e)));
    const source = watchDeckEvents(deckId, e => {
      setEvents(prev => [...prev, e]);
      getDeckState(deckId).then(setState).catch(() => {});
      if (e.step === 'done' && e.variant === null) source.close();
    });
    return () => source.close();
  }, [deckId]);

  const active = state?.variants[variant];
  const plan = active?.plan ?? null;
  // Готовые слайды: по событиям slide-image (сцены сервис сохраняет только в конце варианта).
  const imagesReady = new Set(events.filter(e => e.step === 'slide-image' && e.variant === variant).map(e => e.slide_index)).size;
  const slidesDone = Math.max(active?.scenes.length ?? 0, imagesReady);
  const total = plan?.slides.length ?? 0;
  const otherVariants = VARIANTS.filter(v => v !== variant);
  const variantStatus = useMemo(() => {
    const map: Record<string, string> = {};
    for (const v of VARIANTS) if (state?.variants[v]) map[v] = state.variants[v].status;
    return map;
  }, [state]);
  const steps = useMemo(() => buildSteps(events, variant, otherVariants, plan, slidesDone, variantStatus),
    [events, variant, plan, slidesDone, variantStatus]);
  const planStep = steps[0];

  const failure = active?.status === 'error' ? (active.error || 'Сборка не удалась') : '';
  const noImages = active?.status === 'done' && (!active.slide_images || active.slide_images.length === 0);
  const doneAll = VARIANTS.every(v => state?.variants[v]?.status === 'done');
  const findingsCount = active?.findings.length ?? 0;

  return <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
    {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
    <div className="gen-body">
      <aside className="gen-aside" aria-label="Ход работы">
        <div>
          <span className="gen-request-label">Запрос</span>
          <p className="gen-request-text">{state?.brief || plan?.purpose || ''}</p>
        </div>
        {agentName && <div className="gen-agent"><Boxes size={16} strokeWidth={1.5}/>{agentName}</div>}
        <div className="gen-sep"/>
        {failure ? <div className="gen-error-box" role="alert">
          <span className="gen-step-title strong" style={{ display: 'block', marginBottom: 4 }}>План не составлен</span>
          <span style={{ fontSize: 13, lineHeight: 1.45 }}>{failure}</span>
          <div className="gen-error-actions">
            <button type="button" className="button" onClick={() => { setError(''); setEvents([]); getDeckState(deckId).then(setState); }}>
              <RotateCw size={18} strokeWidth={1.5}/>Повторить
            </button>
            <a className="button" href="#/settings"><Settings size={18} strokeWidth={1.5}/>Агенты и модели</a>
          </div>
        </div> : <ol className="gen-steps" aria-label="Ход работы">
          {steps.map(s => <StepRow key={s.id} step={s} planTitles={plan?.slides.map(x => x.title)}/>)}
        </ol>}
      </aside>
      <div className="gen-main">
        <div className="gen-main-head">
          <div className={`gen-heading ${!plan ? 'muted' : ''}`}>
            <h1>{plan?.title ?? 'Новая презентация'}</h1>
            {doneAll ? <span className="gen-status" role="status">
              <Check size={16} strokeWidth={1.5} color="var(--success)"/>
              Готово: три варианта, {findingsCount} замечаний проверки у варианта 1
            </span> : <span className="gen-sub">Вариант {VARIANTS.indexOf(variant) + 1} из 3</span>}
            {noImages && <div className="gen-note" role="status">
              <AlertTriangle size={18} strokeWidth={1.5} color="var(--text-muted)"/>
              <span>Презентация готова без картинок слайдов: на машине не найден LibreOffice или PowerPoint.
                Файлы pptx и html есть, pdf нет, проверки смысла не было.</span>
            </div>}
          </div>
          {doneAll ? <a className="button primary" href={`#/decks/${deckId}/edit/${variant}`}>Открыть и править</a>
            : !stopped && <button type="button" className="button" onClick={() => { setStopped(true); cancelDeck(deckId).catch(e => setError(String(e))); }}>
              <Square size={18} strokeWidth={1.5}/>Остановить
            </button>}
        </div>
        <div className="gen-grid">
          {Array.from({ length: Math.max(total, active?.slide_images?.length ?? 0) }).map((_, i) => {
            const img = active?.slide_images?.[i];
            const title = plan?.slides[i]?.title ?? '';
            if (img) return <figure key={i} className="gen-slide-figure">
              <img className="gen-slide-img" src={absoluteUrl(img)} alt=""/>
              <figcaption className="gen-slide-caption active">{noImages ? title : i + 1}</figcaption>
            </figure>;
            if (noImages) return <figure key={i} className="gen-slide-figure">
              <div className="gen-slide-text">{title}</div>
              <figcaption className="gen-slide-caption">{i + 1}</figcaption>
            </figure>;
            const building = i === slidesDone && !doneAll;
            if (building) return <figure key={i} className="gen-slide-figure">
              <div className="gen-slide-building">
                <span>{title}</span>
                <span className="gen-skel-line" style={{ width: '60%' }}/>
                <span className="gen-skel-line" style={{ width: '40%' }}/>
                <span className="gen-slide-building-status">верстается</span>
              </div>
              <figcaption className="gen-slide-caption active">{i + 1}. {title}</figcaption>
            </figure>;
            return <figure key={i} className="gen-slide-figure">
              <div className="gen-slide-placeholder"/>
              <figcaption className="gen-slide-caption">{i + 1}{title ? `. ${title}` : ''}</figcaption>
            </figure>;
          })}
        </div>
      </div>
    </div>
  </div>;
}
