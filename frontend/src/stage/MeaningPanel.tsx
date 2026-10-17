import React,{useState} from 'react';
import type {VoiceEditor} from './voiceEditor';
import {MeaningCsvPanel} from './MeaningCsvPanel';

const directions=['Объясни механизм','Добавь контекст','Приведи пример','Покажи последствия','Раскрой доказательства','Упрости для аудитории'];
export function MeaningPanel({editor,refresh}:{editor:VoiceEditor;refresh:()=>void}){
 const m=editor.meaning,[instruction,setInstruction]=useState(''),[error,setError]=useState('');
 const request=(value:string)=>{setError('');void m.request(value,refresh);};
 const change=(edit:()=>void)=>{edit();refresh();};
 const apply=(mode:'update_current'|'create_follow_up')=>{try{m.apply(mode);setError('');refresh();}catch(e){setError(String(e));}};
 const d=m.draft;
 return <aside className="meaning-panel" aria-label="Раскрытие смысла">
  <button className="button" aria-expanded={m.open} onClick={()=>change(()=>{m.open=!m.open;})}>Раскрыть смысл</button>
  {m.open&&<div>
   <p>Выбранный слайд и соседние слайды войдут в контекст. Голосом: «Раскрой смысл: добавь пример» в режиме команд. Данные автора не проходят независимую проверку.</p>
   <MeaningCsvPanel busy={m.busy} onContextChange={()=>{m.invalidateEvidence();refresh();}} onExpand={context=>{setError('');void m.request('Раскрой значение вычисленного изменения для главной мысли выбранного слайда. Используй точную формулу и источник calculation. Не вычисляй числа самостоятельно, не делай неподтверждённых причинных выводов. Покажи ограничения сравнения.',refresh,context);}}/>
   <form onSubmit={e=>{e.preventDefault();request(instruction);}}><label>Что раскрыть<textarea aria-label="Просьба раскрыть смысл" value={instruction} maxLength={3000} onChange={e=>setInstruction(e.target.value)}/></label><button className="button" disabled={m.busy||!instruction.trim()}>Получить черновик</button></form>
   <div className="component-toolbar">{directions.map(value=><button className="button" key={value} disabled={m.busy} onClick={()=>{setInstruction(value);request(value);}}>{value}</button>)}</div>
   {m.busy&&<p role="status">Локальная модель раскрывает мысль… <button className="button" onClick={()=>change(()=>m.cancel())}>Остановить</button></p>}
   {(error||m.error)&&<p role="alert">{error||m.error}</p>}
   {(m.error||m.stale)&&<button className="button" disabled={m.busy} onClick={()=>{setError('');void m.retry(refresh);}}>Пересчитать черновик</button>}
   {d&&<div aria-label="Предпросмотр смыслового черновика">
    <p><strong>Предложение модели. Все формулировки, включая числа и факты, требуют подтверждения и сохранят эту пометку при применении.</strong></p>
    {m.stale&&<p role="alert">Слайд или контекст изменился. Пересчитайте черновик перед применением.</p>}
    <label>Главная мысль<textarea value={d.main_idea} maxLength={1000} onChange={e=>change(()=>{d.main_idea=e.target.value;})}/></label>
    <label>Объяснение<textarea value={d.explanation} maxLength={2000} onChange={e=>change(()=>{d.explanation=e.target.value;})}/></label>
    {d.details.map((item,i)=><fieldset key={i}><legend>Деталь {i+1}</legend><label>Роль<input value={item.role} maxLength={200} onChange={e=>change(()=>{item.role=e.target.value;})}/></label><label>Текст<textarea value={item.text} maxLength={1000} onChange={e=>change(()=>{item.text=e.target.value;})}/></label><label>Связь с мыслью<textarea value={item.supports} maxLength={300} onChange={e=>change(()=>{item.supports=e.target.value;})}/></label><button className="button" onClick={()=>change(()=>{d.details.splice(i,1);})}>Убрать деталь</button></fieldset>)}
    <p>Источники из контекста:</p>{d.evidence.length?<ul>{d.evidence.map((item,i)=><li key={i}>{item.source_id}: «{item.quote}»</li>)}</ul>:<p>Подтверждающих цитат нет.</p>}
    {d.caveats.map((value,i)=><label key={i}>Оговорка {i+1}<textarea value={value} maxLength={2000} onChange={e=>change(()=>{d.caveats[i]=e.target.value;})}/></label>)}
    <p>Рекомендация: {d.recommendation==='create_follow_up'?'создать следующий слайд':'обновить текущий слайд'}. Если текст не помещается, сократите черновик или разделите просьбу.</p>
    {d.slide_draft&&<fieldset><legend>Черновик следующего слайда</legend><label>Заголовок<textarea value={d.slide_draft.title} maxLength={300} onChange={e=>change(()=>{d.slide_draft!.title=e.target.value;})}/></label><label>Содержание<textarea value={d.slide_draft.body} maxLength={4000} onChange={e=>change(()=>{d.slide_draft!.body=e.target.value;})}/></label></fieldset>}
    <p>Обновление заменит заголовок и текстовые блоки выбранного слайда; исходный материал сохранится в заметках и истории.</p>
    <div className="component-toolbar"><button className="button" disabled={m.busy||m.stale} onClick={()=>apply('update_current')}>Применить к текущему</button><button className="button" disabled={m.busy||m.stale} onClick={()=>apply('create_follow_up')}>Создать следующий слайд</button><button className="button" onClick={()=>change(()=>m.reject())}>Отклонить</button></div>
   </div>}
  </div>}
 </aside>;
}
