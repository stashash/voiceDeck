import React,{useEffect,useImperativeHandle,useRef,useState} from 'react';
import {DeckMeaning,type DeckMeaningContext} from './deckMeaning';

export type DeckMeaningPanelHandle={preview:(instruction:string)=>void};
export function DeckMeaningPanel({context,disabled,onApply,ref}:{context:DeckMeaningContext;disabled:boolean;onApply:(prepare:()=>ReturnType<DeckMeaning['application']>)=>Promise<boolean>;ref?:React.Ref<DeckMeaningPanelHandle>}){
 const model=useRef(new DeckMeaning()).current;
 model.update(context);
 const [,render]=useState(0),[open,setOpen]=useState(true),[instruction,setInstruction]=useState(''),[applying,setApplying]=useState(false);
 const refresh=()=>render(n=>n+1);
 useEffect(()=>()=>model.cancel(),[model]);
 const request=(value:string)=>{setInstruction(value);void model.request(value,refresh);};
 useImperativeHandle(ref,()=>({preview:value=>{setOpen(true);request(value);}}));
 const apply=async()=>{
  setApplying(true);model.error='';
  try{model.application();if(await onApply(()=>model.application()))model.reject();}
  catch(e){model.error=String(e);}
  finally{setApplying(false);refresh();}
 };
 const d=model.draft,locked=disabled||applying,hasTarget=!!model.target;
 return <section className="ask-block deck-meaning" aria-label="Раскрытие смысла слайда">
  <div className="deck-meaning-head"><div><span className="deck-meaning-kicker">РАБОТА СО СМЫСЛОМ</span><h3>Углубить мысль слайда</h3></div>
   <button type="button" className="deck-meaning-toggle" aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'Свернуть':'Открыть'}</button></div>
  {open&&<div>
   <ol className="deck-meaning-steps"><li>{hasTarget?'Проверьте цель правки ниже':'Выберите текстовый блок на слайде'}</li><li>Скажите, что добавить или объяснить</li><li>Проверьте черновик и примените его</li></ol>
   <p className="deck-meaning-context">В контекст попадут слайд {context.index+1} и соседние слайды. Черновик не изменит презентацию, пока вы не нажмёте «Применить».</p>
   {hasTarget
    ?<p className="deck-meaning-target" role="status"><strong>{context.selectedId?'Выбранная цель:':'Автоматическая цель:'}</strong> «{model.target!.text.slice(0,140)}{model.target!.text.length>140?'…':''}». {context.selectedId?'Вы выбрали этот блок на слайде.':'Найден единственный основной текстовый блок. Щёлкните другой текст на слайде, чтобы сменить цель.'}</p>
    :<p className="deck-meaning-target" role="status">Сначала выберите один текстовый блок на слайде. Сейчас неясно, куда внести уточнение.</p>}
   {disabled&&<p role="status">Завершите текущую правку или команду. Для применения выберите не более одного текстового блока.</p>}
   <form onSubmit={e=>{e.preventDefault();request(instruction);}}>
    <label>Что раскрыть<textarea aria-label="Просьба раскрыть смысл слайда" value={instruction} maxLength={3000} onChange={e=>setInstruction(e.target.value)}/></label>
    <button className="button primary" disabled={locked||model.busy||!instruction.trim()||!hasTarget}>Подготовить черновик</button>
   </form>
   <div className="chip-row" aria-label="Примеры запросов">{['Объясни механизм','Добавь контекст','Приведи пример','Покажи последствия'].map(value=><button type="button" className="chip" key={value} disabled={locked||model.busy||!hasTarget} onClick={()=>request(value)}>{value}</button>)}</div>
   {model.busy&&<p role="status">Локальная модель раскрывает мысль… <button type="button" className="button" onClick={()=>{model.cancel();refresh();}}>Остановить</button></p>}
   {model.error&&<p role="alert">{model.error}</p>}
   {(model.error||model.stale)&&<button type="button" className="button" disabled={locked||model.busy} onClick={()=>request(model.instruction)}>Пересчитать черновик</button>}
   {d&&<div aria-label="Предпросмотр смыслового черновика">
    <p><strong>Предложение модели. Все формулировки требуют подтверждения автора; пометка сохранится при применении.</strong></p>
    {model.stale&&<p role="alert">Слайд, выбор или контекст изменился. Пересчитайте черновик.</p>}
    <label>Главная мысль<textarea value={d.main_idea} maxLength={1000} onChange={e=>{d.main_idea=e.target.value;refresh();}}/></label>
    <label>Объяснение<textarea value={d.explanation} maxLength={2000} onChange={e=>{d.explanation=e.target.value;refresh();}}/></label>
    {d.details.map((item,i)=><fieldset key={i}><legend>Деталь {i+1}</legend>
     <label>Роль<input value={item.role} maxLength={200} onChange={e=>{item.role=e.target.value;refresh();}}/></label>
     <label>Текст<textarea value={item.text} maxLength={1000} onChange={e=>{item.text=e.target.value;refresh();}}/></label>
     <label>Связь с мыслью<textarea value={item.supports} maxLength={300} onChange={e=>{item.supports=e.target.value;refresh();}}/></label>
     <button type="button" className="button" onClick={()=>{d.details.splice(i,1);refresh();}}>Убрать деталь</button>
    </fieldset>)}
    <p>Источники из контекста:</p>{d.evidence.length?<ul>{d.evidence.map((e,i)=><li key={i}>{e.source_id}: «{e.quote}»</li>)}</ul>:<p>Подтверждающих цитат нет.</p>}
    {d.caveats.map((value,i)=><label key={i}>Оговорка {i+1}<textarea value={value} maxLength={2000} onChange={e=>{d.caveats[i]=e.target.value;refresh();}}/></label>)}
    <p>{model.target?`Будет заменён только текст блока «${model.target.text.slice(0,80)}».`:'Выберите один текстовый блок на слайде и пересчитайте черновик.'} Предыдущий текст доступен через отмену правки. Если текст не помещается, сократите черновик.</p>
    <p>Рекомендация модели: {d.recommendation==='create_follow_up'?'отдельный следующий слайд (создайте его вручную)':'обновить текущий слайд'}.</p>
    <button type="button" className="button" disabled={locked||model.busy||model.stale||!model.target||!context.active.revision} onClick={()=>void apply()}>{applying?'Сохранение…':'Применить к текстовому блоку'}</button>
    <button type="button" className="button" disabled={applying} onClick={()=>{model.reject();refresh();}}>Отклонить</button>
   </div>}
  </div>}
 </section>;
}
