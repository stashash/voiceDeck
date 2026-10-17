import type {DeckVariantState} from '../designer/api';
import {editorRequest} from './editorRequest';
import {meaningCommand,validMeaningDraft,type MeaningDraft} from './meaningExpansion';

export type DeckMeaningContext={deckId:string;variant:string;active:DeckVariantState;index:number;selectedId:string|null;unsaved:string};
export const deckMeaningKey=(c:DeckMeaningContext)=>JSON.stringify(c);
export const meaningInstructionHint='Уточните просьбу, например: «Раскрой смысл: объясни механизм».';
/** Returning true consumes the intent before the ordinary command/rewrite path. */
export function routeDeckMeaningCommand(raw:string,preview:(instruction:string)=>void){
 const instruction=meaningCommand(raw);
 if(instruction===undefined)return false;
 preview(instruction.trim());return true;
}

/** A server-backed deck preview, deliberately independent of VoiceEditor document mutations. */
export class DeckMeaning {
 draft?:MeaningDraft;busy=false;error='';instruction='';
 private generation=0;private key='';private snapshot=-1;private serial=0;private controller?:AbortController;
 private sources:Record<string,string>={};
 context!:DeckMeaningContext;
 update(context:DeckMeaningContext){const key=deckMeaningKey(context);if(key!==this.key){this.key=key;this.generation++;this.cancel();}this.context=context;}
 get stale(){return !!this.draft&&this.snapshot!==this.generation;}
 cancel(){this.serial++;this.controller?.abort();this.busy=false;}
 reject(){this.cancel();this.draft=undefined;this.error='';}
 async request(instruction:string,changed:()=>void){
  if(!instruction.trim()){this.error=meaningInstructionHint;changed();return;}
  this.cancel();const serial=this.serial,context=structuredClone(this.context),generation=this.generation;
  const source=context.active.scenes[context.index];if(!source)return;
  if(!this.target){this.error='Выберите один текстовый блок на слайде и повторите запрос. Если нужно уточнить заголовок, выберите его прямо на слайде.';changed();return;}
  const controller=new AbortController();this.controller=controller;this.busy=true;this.error='';this.instruction=instruction;changed();
  const sources=Object.fromEntries(context.active.scenes.slice(Math.max(0,context.index-1),context.index+2).map(scene=>[scene.slide_id,[scene.notes,context.active.plan?.slides.find(p=>p.id===scene.slide_id)?.notes,...scene.elements.map(e=>e.text)].filter(Boolean).join('\n')]));
  try{
   const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(deckMeaningKey(context)));
   const version=Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('');
   if(serial!==this.serial)return;
   const draft=await editorRequest<MeaningDraft>('meaning/expand',{instruction,slide_id:source.slide_id,version,context:{sources,current_slide:source.slide_id,slides:context.active.scenes.map(s=>({id:s.slide_id,title:s.elements.find(e=>/title|heading/i.test(e.role))?.text})),design_id:context.active.design_system_id}},{signal:controller.signal,timeout:32000});
   if(serial!==this.serial)return;
   if(!validMeaningDraft(draft)||draft.slide_id!==source.slide_id||draft.version!==version||draft.evidence.some(e=>!sources[e.source_id]?.includes(e.quote)))throw Error('Некорректный черновик или источник. Повторите просьбу.');
   this.draft=structuredClone(draft);this.snapshot=generation;this.sources=sources;
  }catch(e){if(serial===this.serial)this.error=String(e)+' Презентация не изменена.';}
  finally{if(serial===this.serial){this.busy=false;changed();}}
 }
 get target(){
  const {active,index,selectedId}=this.context,scene=active.scenes[index];
  if(!scene)return;
  if(selectedId)return scene.elements.find(e=>e.id===selectedId&&e.type==='text');
  const body=scene.elements.filter(e=>e.type==='text'&&!/^(title|heading|заголовок)$/i.test(e.role));
  return body.length===1?body[0]:undefined;
 }
 application(){
  if(!this.draft||this.busy)throw Error('Дождитесь черновика');
  if(this.stale)throw Error('Слайд, выбор или контекст изменился. Пересчитайте черновик.');
  const d=this.draft;
  if(!validMeaningDraft(d)||d.evidence.some(e=>!this.sources[e.source_id]?.includes(e.quote)))throw Error('Проверьте поля и источники черновика');
  const target=this.target;if(!target)throw Error('Выберите один текстовый блок слайда и пересчитайте черновик.');
  if(!this.context.active.revision)throw Error('Версия презентации неизвестна. Обновите страницу.');
  const text=['Требует подтверждения автора — предложенная формулировка:',d.main_idea,d.explanation,...d.details.map(x=>`${x.role}: ${x.text}\nСвязь с мыслью: ${x.supports}`),...d.evidence.map(e=>`Данные автора (${e.source_id}): «${e.quote}»`),...d.caveats.map(x=>'Оговорка: '+x)].join('\n\n');
  if(text.length>1800||text.split('\n').reduce((n,s)=>n+Math.max(1,Math.ceil(s.length/90)),0)>17)throw Error('Слишком много текста для одного блока. Сократите черновик.');
  return {element_id:target.id,text,expected_revision:this.context.active.revision,target_slide_id:d.slide_id};
 }
}
