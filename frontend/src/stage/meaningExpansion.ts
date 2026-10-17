import type {VoiceEditor,Page} from './voiceEditor';
import {editorRequest} from './editorRequest';
import type {CsvCalculation} from './meaningCsv';

export type MeaningEvidenceContext={sources:Record<string,string>;calculation:CsvCalculation};

export type MeaningDraft={main_idea:string;explanation:string;details:{text:string;role:string;supports:string}[];evidence:{source_id:string;quote:string}[];caveats:string[];recommendation:'update_current'|'create_follow_up';slide_draft:{title:string;body:string}|null;verification:'requires_confirmation';slide_id:string;version:string};
const fingerprint=(editor:VoiceEditor)=>JSON.stringify({pages:editor.document.pages,designId:editor.document.designId});
const textOf=(p:Page)=>[p.notes??'',...p.components.map(c=>[c.text,c.rows?.map(row=>row.join(' | ')).join('\n'),c.labels?.map((label,i)=>`${label}: ${c.values?.[i]??''}`).join('\n')].filter(Boolean).join('\n'))].filter(Boolean).join('\n');
export function meaningCommand(raw:string){return raw.trim().replace(/^команда\s*[:,.]?\s*/i,'').match(/^(?:раскрой|раскрыть|расширь)\s+(?:смысл|мысль)(?:\s+слайда)?\s*[:,—-]?\s*(.*)$/i)?.[1];}

export function validMeaningDraft(value:unknown):value is MeaningDraft{
 const d=value as MeaningDraft;
 const str=(s:unknown,max:number)=>typeof s==='string'&&s.trim().length>0&&s.length<=max;
 return !!d&&str(d.main_idea,1000)&&str(d.explanation,2000)&&Array.isArray(d.details)&&d.details.length<=8&&d.details.every(x=>x&&str(x.text,1000)&&str(x.role,200)&&str(x.supports,300))&&Array.isArray(d.evidence)&&d.evidence.length<=12&&d.evidence.every(x=>x&&str(x.source_id,100)&&str(x.quote,1000))&&Array.isArray(d.caveats)&&d.caveats.length<=12&&d.caveats.every(x=>str(x,2000))&&['update_current','create_follow_up'].includes(d.recommendation)&&(d.slide_draft===null||!!d.slide_draft&&str(d.slide_draft.title,300)&&str(d.slide_draft.body,4000))&&d.verification==='requires_confirmation'&&str(d.slide_id,100)&&str(d.version,64);
}

/** Preview lives outside Document. Every accepted model assertion remains labelled. */
export class MeaningExpansion{
 draft?:MeaningDraft;busy=false;error='';instruction='';open=false;
 private serial=0;private controller?:AbortController;private snapshot='';private source?:Page;private document?:VoiceEditor['document'];
 private requestEvidence?:MeaningEvidenceContext;private draftEvidence?:MeaningEvidenceContext;private evidenceInvalid=false;
 constructor(private editor:VoiceEditor){}
 cancel(){this.serial++;this.controller?.abort();this.busy=false;}
 reject(){this.cancel();this.draft=undefined;this.error='';this.open=false;}
 invalidateEvidence(){if(this.requestEvidence){this.cancel();this.evidenceInvalid=true;}if(this.draftEvidence)this.evidenceInvalid=true;}
 retry(changed:()=>void){if(this.evidenceInvalid){this.error='Параметры CSV изменились. Подтвердите сопоставимость и нажмите «Раскрыть смысл вычисленного результата» для нового расчёта.';changed();return Promise.resolve();}return this.request(this.instruction,changed,this.requestEvidence);}
 get stale(){return !!this.draft&&(this.evidenceInvalid||this.document!==this.editor.document||this.snapshot!==fingerprint(this.editor)||this.editor.current.id!==this.draft.slide_id);}
 async request(instruction:string,changed:()=>void,evidence?:MeaningEvidenceContext){
  if(!instruction.trim())return;
  this.cancel();const serial=this.serial,controller=new AbortController();this.controller=controller;
  this.instruction=instruction;this.open=true;this.busy=true;this.error='';changed();
  const extra=evidence?structuredClone(evidence):undefined;this.requestEvidence=extra;
  const source=structuredClone(this.editor.current),snapshot=fingerprint(this.editor),document=this.editor.document;
  const index=document.index,nearby=document.pages.slice(Math.max(0,index-1),index+2);
  const sources={...Object.fromEntries(nearby.map(p=>[p.id,textOf(p)])),...extra?.sources};
  try{
   const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify({snapshot,evidence:extra})));
   const version=Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('');
   const result=await editorRequest<MeaningDraft>('meaning/expand',{instruction,slide_id:source.id,version,context:{sources,calculation:extra?.calculation,current_slide:source.id,slides:document.pages.map(p=>({id:p.id,title:p.components.find(c=>c.kind==='title')?.text})),design_id:document.designId}},{signal:controller.signal,timeout:32000});
   if(serial!==this.serial)return;
   if(!validMeaningDraft(result)||result.slide_id!==source.id||result.version!==version||result.evidence.some(e=>!sources[e.source_id]?.includes(e.quote)))throw Error('Некорректный черновик или источник. Повторите просьбу.');
   this.draft=structuredClone(result);this.snapshot=snapshot;this.source=source;this.document=document;this.draftEvidence=extra;this.evidenceInvalid=false;
  }catch(error){if(serial===this.serial)this.error=String(error)+' Документ не изменён. Повторите или уточните просьбу.';}
  finally{if(serial===this.serial){this.busy=false;changed();}}
 }
 apply(mode:'update_current'|'create_follow_up'){
  const d=this.draft,e=this.editor;
  if(!d||this.busy)throw Error('Дождитесь черновика');
  if(this.stale)throw Error('Слайд или контекст изменился. Пересчитайте черновик.');
  if(!validMeaningDraft(d))throw Error('Проверьте заполнение и длину полей черновика');
  const title=mode==='create_follow_up'&&d.slide_draft?d.slide_draft.title:d.main_idea;
  const body=[d.explanation,...d.details.map(x=>`${x.role}: ${x.text}\nСвязь с мыслью: ${x.supports}`),mode==='create_follow_up'?d.slide_draft?.body:undefined,...d.caveats.map(x=>'Оговорка: '+x)].filter(Boolean).join('\n\n');
  // Labels are added at the write boundary, so editing the preview cannot remove them.
  const content='Требует подтверждения автора — предложенная формулировка:\n'+title+'\n\n'+body;
  const lines=content.split('\n').reduce((sum,line)=>sum+Math.max(1,Math.ceil(line.length/90)),0);
  if(content.length>1800||lines>17||title.length>100)throw Error('Слишком много текста для одного слайда. Сократите черновик или разделите просьбу.');
  if(mode==='update_current'&&e.current.components.some(c=>c.locked&&['title','text','card'].includes(c.kind)))throw Error('Текст слайда заблокирован. Создайте следующий слайд.');
  const backup=structuredClone(e.document),undo=[...e.undoStack],redo=[...e.redoStack];
  const evidenceNotes=[...d.evidence.map(x=>`Данные автора (${x.source_id}): ${x.quote}`),...Object.entries(this.draftEvidence?.sources??{}).map(([id,text])=>`Воспроизводимый расчёт из CSV (${id}):\n${text}`)];
  try{
   e.checkpoint();
   if(mode==='create_follow_up'){
    e.document.pages.splice(e.document.index+1,0,{id:crypto.randomUUID(),background:this.source!.background,components:[]});e.document.index++;
   }
   if(mode==='update_current'){
    e.current.notes=[e.current.notes,'Исходный материал автора:\n'+textOf(this.source!),...evidenceNotes].filter(Boolean).join('\n\n');
    e.current.components=e.current.components.filter(c=>!['title','text','card'].includes(c.kind));
    e.add('title','Не подтверждено: '+title);
    const item=e.add('text',content);Object.assign(item,{x:64,y:180,width:1152,height:460,size:22});
   }else{
    e.add('title','Не подтверждено: '+title);const item=e.add('text',content);Object.assign(item,{x:64,y:180,width:1152,height:460,size:22});
    e.current.notes=evidenceNotes.join('\n');e.applyLayout();
   }
   e.notice='Смысловой черновик применён. Предложения требуют подтверждения автора.';e.save();this.reject();
  }catch(error){e.document=backup;e.undoStack=undo;e.redoStack=redo;throw error;}
 }
}
