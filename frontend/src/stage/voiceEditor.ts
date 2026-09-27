import type {Slide} from '../store';
import {BASE_URL,DesignSystem,Pattern} from '../designer/api';
import {applyPlan,Plan} from './editorOperations';
import {quickVoice} from './quickVoice';
import {contentHtml,mediaUrl} from './componentContent';
import {editorRequest,EditorServiceError} from './editorRequest';
import {prepareEditorModel} from './editorModel';
import {contextPages} from './editorContext';
import {parseTextVoice} from './textVoice';

export type Component={voiceNumber?:number;id:string;kind:'title'|'text'|'image'|'card'|'shape'|'table'|'chart';text:string;size:number;color:string;side:'left'|'right';url?:string;x:number;y:number;width:number;height:number;fill:string;font?:string;attribution?:string;bold?:boolean;italic?:boolean;locked?:boolean;align?:'left'|'center'|'right';rotation?:number;opacity?:number;radius?:number;borderColor?:string;borderWidth?:number;fit?:'contain'|'cover';rows?:string[][];labels?:string[];values?:number[];group?:string;sourceShapeId?:number};
export type Page={nextVoiceNumber?:number;id:string;components:Component[];background:string;notes?:string;backgroundUrl?:string};
export type Document={pages:Page[];index:number;selected:string|null;selectedIds?:string[];designId?:string;schemaVersion?:number};
const page=():Page=>({id:crypto.randomUUID(),components:[],background:'#f7f5fa'});
const escape=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const colors:Record<string,string>={'красный':'#dc2626','синий':'#2563eb','фиолетовый':'#7654ff','черный':'#17141f','белый':'#ffffff','зеленый':'#15803d'};

/** Deterministic commands operate only on final utterances; every edit is reversible. */
export class VoiceEditor{
 showNumbers=true;
 lastMove?:{ids:string[];dx:number;dy:number;snapshot:string};
 mode:'control'|'dictation'='control';
 design?:DesignSystem;
 imageResults:{url:string;title:string;source:string;author:string;license:string}[]=[];
 imagePrompt='';imageOffset=0;imageBusy=false;thinking=false;
 imageTarget?:{page:string;component?:string};
 private imageRequest=0;
 private active?:AbortController;
 private activeRequest?:string;
 private imageController?:AbortController;
 private requestVersion=0;
 private queue:{command:string;pageId:string;selected:string[];changed:()=>void;done:()=>void}[]=[];
 get queued(){return this.queue.length;}
 onSave?:()=>void;
 private pendingText?:{pageId:string;ids:string[];selection:string[];snapshot:string};
 get waitingForText(){return !!this.pendingText;}
 cancelText(){this.pendingText=undefined;this.notice='Ввод текста отменён';}
 private writeText(items:Component[],text:string,append=false){
  const updates=items.map(item=>({item,text:append?[item.text.trimEnd(),text].filter(Boolean).join(' '):text}));
  if(updates.some(({item,text})=>item.locked||!['title','text','card'].includes(item.kind)||text.length>12000))throw Error('Текст нельзя изменить: проверьте тип, блокировку и длину');
  this.checkpoint();
  for(const update of updates)update.item.text=update.text;
  this.notice='Текст заменён';
 }
 cancel(){
  this.pendingText=undefined;
  this.requestVersion++;this.active?.abort();this.active=undefined;this.thinking=false;
  if(this.activeRequest)void editorRequest('intent/'+this.activeRequest+'/cancel',{}, {timeout:2000}).catch(()=>{});
  this.activeRequest=undefined;
  for(const job of this.queue.splice(0))job.done();
  this.imageRequest++;this.imageController?.abort();this.imageBusy=false;this.notice='Обработка остановлена';
 }
 lastRequest='';pendingQuestion='';
 enqueue(raw:string,changed:()=>void){void this.interpret(raw,changed).catch(e=>{this.notice=String(e);changed();});}
 async interpret(raw:string,changed:()=>void){
  const c=raw.trim().replace(/^команда\s*[:,.]?\s*/i,'').replace(/[.!?]+$/,'').trim();
  if(!c)return;
  if(this.pendingText){
   if(/^(?:стоп|отмена|отмени|отмени диктовку)$/i.test(c)){this.cancelText();changed();return;}
   const pending=this.pendingText;this.pendingText=undefined;
   if(pending.pageId!==this.current.id||JSON.stringify(this.selectedIds)!==JSON.stringify(pending.selection)||pending.snapshot!==JSON.stringify(this.current.components.filter(item=>pending.ids.includes(item.id)))){this.notice='Выбранный текст изменился. Ввод отменён';changed();return;}
   this.writeText(this.current.components.filter(item=>pending.ids.includes(item.id)),raw.trim());
   this.save();changed();return;
  }
  if(/^(стоп|остановись|отмени генерацию)$/i.test(c)||(/^(отмени|отмена)$/i.test(c)&&this.thinking)){this.cancel();changed();return;} if(/^управляю|^режим управления/i.test(c)){this.mode='control';this.notice='Управление слайдом';changed();return;}
  if(/^диктуй|^диктую|^режим диктовки/i.test(c)){this.mode='dictation';this.notice='Диктовка в выбранный компонент';changed();return;}
  if(/^запиши в заголовок\s+/i.test(c)){this.command(c.replace(/^запиши в заголовок/i,'заголовок'));this.save();changed();return;}
  if(this.mode==='dictation'&&!/^команда/i.test(raw)){if(this.selected?.locked){this.notice='Объект заблокирован';changed();return;}this.checkpoint();if(this.selected&&['text','title','card'].includes(this.selected.kind))this.selected.text+=(this.selected.text?' ':'')+raw;else this.add('text',raw);this.notice='Текст записан';this.save();changed();return;}
  this.ensureNumbers();
  const textAction=parseTextVoice(raw);
  if(textAction){
   const numbered=textAction.elementNumber===undefined?undefined:this.current.components.find(item=>item.voiceNumber===textAction.elementNumber);
   if(textAction.elementNumber!==undefined&&!numbered){this.notice='Такого номера нет на этом слайде';changed();return;}
   const ids=numbered?[numbered.id]:this.selectedIds;
   const items=this.current.components.filter(item=>ids.includes(item.id));
   if(!items.length||items.some(item=>!['title','text','card'].includes(item.kind))){this.notice='Не выбран текстовый элемент';changed();return;}
   if(items.some(item=>item.locked))throw Error('Объект заблокирован');
   if(numbered)this.selectMany(ids);
   this.pendingQuestion='';
   if(textAction.kind==='textStart'){
    this.pendingText={pageId:this.current.id,ids:[...ids],selection:[...this.selectedIds],snapshot:JSON.stringify(items)};
    this.notice='Ожидается новый текст';changed();return;
   }
   this.writeText(items,textAction.text,textAction.kind==='appendText');
   this.save();changed();return;
  }
  const media=c.match(/^(найди|подбери|сгенерируй)\s+(?:изображение|фотографию|картинку|иллюстрацию)\s+(.+)$/i);
  if(media){void this.images(media[2],media[1].toLowerCase()==='сгенерируй',changed);return;}
  if(/^ещ[её] варианты$/i.test(c)){this.imageOffset+=6;void this.images(this.imagePrompt,false,changed,true);return;}
  const choose=c.match(/^(?:возьми|выбери)\s+(первую|вторую|третью|четвертую|пятую|шестую|[1-6])$/i);
  if(choose&&this.imageResults.length){this.pickImage(Number(choose[1])||['первую','вторую','третью','четвертую','пятую','шестую'].indexOf(choose[1].toLowerCase())+1);this.save();changed();return;}
  if(quickVoice(this,raw.trim().replace(/^команда\s*[:,.]?\s*/i,''))){this.pendingQuestion='';this.save();changed();return;}
  // Only unambiguous transport actions bypass planning. Content instructions all use the document model.
  if(/^(отмени|отмена|верни|повтори|покажи залу)$/i.test(c)){this.command(c);this.save();changed();return;}
  if(this.queue.length>=4){this.notice='Очередь заполнена. Дождитесь ответа или скажите «Стоп».';changed();return;}
  await new Promise<void>(done=>{this.queue.push({command:c,pageId:this.current.id,selected:[...this.selectedIds],changed,done});void this.drain();});
 }
 private async drain(){
  if(this.thinking)return;
  const job=this.queue.shift();if(!job)return;
  try{await this.plan(job.command,job.pageId,job.selected,job.changed);}finally{job.done();void this.drain();}
 }
 private async plan(c:string,pageId:string,selection:string[],changed:()=>void){
  const source=this.document.pages.find(p=>p.id===pageId);
  if(!source){this.notice='Слайд команды удалён';changed();return;}
  const version=this.requestVersion,controller=new AbortController(),requestId=crypto.randomUUID();
  this.active=controller;this.activeRequest=requestId;this.thinking=true;this.notice='Обрабатываю: '+c;changed();
  const included=contextPages(c,this.document,pageId);
  const snapshots=included.map(p=>({id:p.id,data:JSON.stringify(p)})),order=this.document.pages.map(p=>p.id).join(',');
  const contextDocument={pages:structuredClone(included),index:included.indexOf(source),selected:selection[0]??null,selectedIds:selection};
  const ids=new Map<string,string>();
  let number=0;for(const p of contextDocument.pages)p.components.forEach(item=>{const id=`e${++number}`;ids.set(id,item.id);contextDocument.selectedIds=contextDocument.selectedIds.map(v=>v===item.id?id:v);if(contextDocument.selected===item.id)contextDocument.selected=id;item.id=id;});
  const context=JSON.stringify({document:contextDocument,currentSlide:this.document.pages.indexOf(source)+1,slides:this.document.pages.map((p,i)=>({id:p.id,index:i+1,title:p.components.find(c=>c.kind==='title')?.text.slice(0,100)})),design:this.design?{font:this.design.tokens.fonts[0]?.family,background:this.color('background','#ffffff'),text:this.color('text','#17141f'),accent:this.color('accent','#2563eb'),surface:this.color('surface','#e8e1ff')}:undefined},(key,value)=>['url','backgroundUrl','attribution'].includes(key)?undefined:value);
  try{
   const request=this.pendingQuestion?`Предыдущая просьба: ${this.lastRequest}. Уточнение: ${this.pendingQuestion}. Ответ: ${c}`:c;
   if(context.length>24000)throw Error('Контекст слайда слишком велик. Используйте точную команду или разделите слайд.');
   const send=()=>editorRequest<Plan>('intent',{request_id:requestId,instruction:request,context},{signal:controller.signal,timeout:35000});
   let result:Plan;
   try{result=await send();}catch(error){
    if(!(error instanceof EditorServiceError)||error.code!=='model_loading')throw error;
    await prepareEditorModel(controller.signal,status=>{if(version===this.requestVersion){this.notice=status.state==='ready'?'Обрабатываю: '+c:'Загружаю модель. Команда ожидает; локальные правки доступны.';changed();}});
    if(version!==this.requestVersion)return;
    if(snapshots.some(p=>p.data!==JSON.stringify(this.document.pages.find(current=>current.id===p.id))))throw Error('Слайд изменился во время загрузки. Повторите просьбу.');
    result=await send();
   }
   if(version!==this.requestVersion)return;
   for(const op of result.operations??[])if(op.targets)op.targets=op.targets.map(id=>ids.get(id)??id);
   if(snapshots.some(p=>p.data!==JSON.stringify(this.document.pages.find(current=>current.id===p.id)))||order!==this.document.pages.map(p=>p.id).join(',')){this.notice='Слайд изменился во время обработки. Повторите просьбу.';return;}
   if(result.clarification){this.lastRequest=request;this.pendingQuestion=result.clarification;this.notice=result.clarification;return;}
   this.pendingQuestion='';
   if(!Array.isArray(result.operations)||!result.operations.length){this.notice='Уточните, что изменить на слайде';return;}
   const previous={page:this.current.id,selected:this.document.selected,ids:this.document.selectedIds};
   const moved=previous.page!==pageId||JSON.stringify(this.selectedIds)!==JSON.stringify(selection);
   this.document.index=this.document.pages.findIndex(p=>p.id===pageId);this.document.selected=selection[0]??null;this.document.selectedIds=selection;
   try{
    const special=result.operations.filter(o=>['search','generate','pick_image','publish','undo','redo'].includes(o.op));
    if(special.length){
     if(result.operations.length!==1)throw Error('Разделите изменение слайда и поиск/показ на две просьбы');
     const op=special[0];if(op.targets?.length&&op.targets[0]!=='selected'){if(!this.current.components.some(c=>c.id===op.targets![0]))throw Error('Целевое изображение не найдено');this.select(op.targets[0]);}
     if(op.op==='search'||op.op==='generate')void this.images(op.value??'',op.op==='generate',changed);
     else if(op.op==='pick_image')this.pickImage(op.index??1);else if(op.op==='publish')this.publish();else if(op.op==='undo')this.undo();else this.redo();
    }else applyPlan(this,result);
   }finally{if(moved){const i=this.document.pages.findIndex(p=>p.id===previous.page);if(i>=0){this.document.index=i;this.document.selected=previous.selected;this.document.selectedIds=previous.ids;}}}
   this.save();
  }catch(e){if(version===this.requestVersion){this.notice=String(e);void editorRequest('intent/'+requestId+'/cancel',{}, {timeout:2000}).catch(()=>{});}}
  finally{if(version===this.requestVersion){this.thinking=false;this.active=undefined;this.activeRequest=undefined;}changed();}
 }
 async images(prompt:string,generate:boolean,changed:()=>void,more=false){
  this.imageController?.abort();this.imageController=new AbortController();
  const request=++this.imageRequest;this.imageBusy=true;this.imagePrompt=prompt;if(!more){this.imageOffset=0;this.imageTarget={page:this.current.id,component:this.selected?.kind==='image'?this.selected.id:undefined};}this.notice=generate?'Генерирую изображение…':'Ищу изображения…';changed();
  try{const data=await editorRequest<{items:VoiceEditor['imageResults']}>(generate?'images/generate':'images/search',{prompt,offset:this.imageOffset,style:this.design?`Presentation illustration. Palette: ${this.design.tokens.colors.filter(c=>c.source==='usage').slice(0,6).map(c=>'#'+c.hex).join(', ')}. No text.`:'',landscape:!this.selected||this.selected.width>=this.selected.height},{signal:this.imageController.signal,timeout:generate?190000:30000});if(request!==this.imageRequest)return;this.imageResults=data.items;this.notice=data.items.length?'Выберите вариант кнопкой или скажите «Возьми вторую»':'Ничего не найдено. Попробуйте другой запрос.';
  }catch(e){if(request===this.imageRequest)this.notice=String(e);}finally{if(request===this.imageRequest){this.imageBusy=false;changed();}}
 }
 pickImage(number:number){const item=this.imageResults[number-1];if(!item){this.notice='Такого варианта нет';return;}if(this.imageTarget?.page!==this.current.id){this.notice='Вернитесь на слайд, для которого искали изображение';return;}let target=this.current.components.find(x=>x.id===this.imageTarget?.component);if(this.imageTarget?.component&&!target){this.notice='Исходное изображение удалено. Повторите поиск.';return;}this.checkpoint();target??=this.add('image',item.title);target.url=item.url;target.attribution=[item.author,item.license,item.source].filter(Boolean).join(' · ');this.document.selected=target.id;this.notice='Изображение вставлено';this.save();}
 color(role:string,fallback:string){const tokens=this.design?.tokens.colors??[];const c=tokens.find(c=>c.role===role&&c.source==='usage')??tokens.find(c=>c.role===role);return c?'#'+c.hex.replace('#',''):fallback;}
 ensureContrast(c:Component){
  const luminance=(hex:string)=>{const rgb=hex.replace('#','').match(/../g)?.map(x=>parseInt(x,16)/255);return rgb?.length===3?rgb.map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0):1;};
  const bg=luminance(c.fill==='transparent'?this.current.background:c.fill),fg=luminance(c.color);
  if((Math.max(bg,fg)+.05)/(Math.min(bg,fg)+.05)<4.5)c.color=bg>.179?'#17141f':'#ffffff';
 }
 applyDesign(ds:DesignSystem){this.checkpoint();this.design=ds;this.document.designId=ds.id;for(const p of this.document.pages){p.background=this.color('background','#f7f5fa');for(const c of p.components){if(c.locked)continue;c.font=ds.tokens.fonts.find(f=>f.role==='body')?.family??ds.tokens.fonts[0]?.family??'Arial';c.color=this.color('text','#17141f');if(c.kind==='card')c.fill=this.color('surface','#e8e1ff');if(c.kind==='shape')c.fill=this.color('accent','#7654ff');const step=ds.tokens.type_scale.find(x=>x.role===(c.kind==='title'?'display':'body'));if(step)c.size=Math.max(18,step.size_pt*4/3);}}this.applyLayout();this.notice=`Применена дизайн-система: ${ds.name??ds.id}`;}
 applyLayout(pattern?:Pattern){
  const cards=this.current.components.filter(c=>c.kind==='card'&&!c.locked);
  const p=pattern??this.design?.patterns.find(p=>cards.length>0&&(p.groups?.[0]?.units?.length??0)>=cards.length)??this.design?.patterns.find(p=>p.kind==='title');if(!p)return;
  const title=this.current.components.find(c=>c.kind==='title'&&!c.locked),slot=p.slots?.find(s=>s.role==='title');
  if(title&&slot){this.update(title.id,{x:slot.box[0]*1280,y:slot.box[1]*720,width:slot.box[2]*1280,height:slot.box[3]*720},false);if(slot.style){if(slot.style.family)title.font=slot.style.family;if(slot.style.size_pt)title.size=slot.style.size_pt*4/3;if(slot.style.color)title.color='#'+slot.style.color.replace('#','');if(slot.style.bold!==undefined)title.bold=slot.style.bold;}}
  const group=p.groups?.find(g=>g.units.length>=cards.length);if(!group)return;
  const linked=[group,...(p.groups??[]).filter(g=>g.id&&group.linked_group_ids?.includes(g.id))];
  cards.forEach((c,i)=>{const boxes=linked.map(g=>g.units[i]?.box).filter(Boolean);const x=Math.min(...boxes.map(b=>b[0])),y=Math.min(...boxes.map(b=>b[1]));const right=Math.max(...boxes.map(b=>b[0]+b[2])),bottom=Math.max(...boxes.map(b=>b[1]+b[3]));this.update(c.id,{x:x*1280,y:y*720,width:(right-x)*1280,height:Math.max(80,(bottom-y)*720)},false);});
 }
 document:Document={pages:[page()],index:0,selected:null};
 undoStack:Document[]=[];redoStack:Document[]=[];
 private historyWeights=new WeakMap<Document,number>();
 limitHistory(history:Document[]){let bytes=0;return history.slice(-100).reverse().filter(d=>{let weight=this.historyWeights.get(d);if(weight===undefined){weight=JSON.stringify(d).length*2;this.historyWeights.set(d,weight);}bytes+=weight;return bytes<=8*1024*1024;}).reverse();}
 notice='Опишите, что создать или изменить. Для ввода текста включите «Диктую текст».';
 published:Slide|null=null;
 private revision=0;
 get current(){return this.document.pages[this.document.index];}
 ensureNumbers(){for(const p of this.document.pages){let next=Math.max(p.nextVoiceNumber??1,...p.components.map(c=>(c.voiceNumber??0)+1));const used=new Set<number>();for(const c of p.components){if(!Number.isInteger(c.voiceNumber)||c.voiceNumber!<1||used.has(c.voiceNumber!))c.voiceNumber=next++;used.add(c.voiceNumber!);}p.nextVoiceNumber=next;}}
 get selectedIds(){const primary=this.document.selected;if(!primary)return [];const ids=this.document.selectedIds;return (ids?.[0]===primary?ids:[primary]).filter(id=>this.current.components.some(c=>c.id===id));}
 selectMany(ids:string[]){this.lastMove=undefined;const groups=new Set(this.current.components.filter(c=>ids.includes(c.id)&&c.group).map(c=>c.group));const selected=this.current.components.filter(c=>ids.includes(c.id)||c.group&&groups.has(c.group));this.document.selectedIds=selected.map(c=>c.id);this.document.selected=selected[0]?.id??null;this.notice=selected.length?'Выбраны номера: '+selected.map(c=>c.voiceNumber).join(', '):'Выделение снято';}
 get selected(){return this.current.components.find(c=>c.id===this.document.selected);}
 checkpoint(){this.undoStack=this.limitHistory([...this.undoStack,structuredClone(this.document)]);this.redoStack=[];}
 add(kind:Component['kind'],text:string){const c:Component={id:crypto.randomUUID(),kind,text,size:kind==='title'?44:26,color:this.color('text','#17141f'),font:this.design?.tokens.fonts[0]?.family??'Arial',side:kind==='image'?'right':'left',x:kind==='image'?650:64,y:kind==='title'?50:180+(this.current.components.filter(c=>c.kind!=='title').length%4)*90,width:kind==='title'?1152:kind==='text'?530:320,height:kind==='title'?100:kind==='text'?80:220,fill:kind==='card'?this.color('surface','#e8e1ff'):kind==='shape'?this.color('accent','#7654ff'):'transparent'};const size=this.design?.tokens.type_scale.find(s=>s.role===(kind==='title'?'display':'body'));if(size)c.size=Math.max(18,size.size_pt*4/3);this.ensureContrast(c);this.current.components.push(c);this.ensureNumbers();this.document.selectedIds=[c.id];this.document.selected=c.id;return c;}
 update(id:string,patch:Partial<Component>,record=true){const c=this.current.components.find(c=>c.id===id);if(!c)return;if(c.locked&&!(patch.locked===false&&Object.keys(patch).length===1))throw Error('Объект заблокирован');if(record)this.checkpoint();Object.assign(c,patch);c.width=Math.max(50,Math.min(1280,c.width));c.height=Math.max(40,Math.min(720,c.height));c.x=Math.max(0,Math.min(1280-c.width,c.x));c.y=Math.max(0,Math.min(720-c.height,c.y));}
 save(){this.ensureNumbers();if(this.onSave){this.onSave();return;}try{localStorage.setItem('voicedeck-editor-v2',JSON.stringify(this.document));}catch{this.notice='Не удалось сохранить документ в браузере: возможно, изображения слишком велики.';}}
 restore(){try{const d=JSON.parse(localStorage.getItem('voicedeck-editor-v2')??'null');if(d?.pages?.length&&d.pages.every((p:Page)=>Array.isArray(p.components)&&p.components.every(c=>Number.isFinite(c.x)&&Number.isFinite(c.width)))&&d.index>=0&&d.index<d.pages.length)this.document=d;this.ensureNumbers();}catch{/* A damaged or absent draft must not prevent opening the editor. */}}
 select(id:string){this.selectMany([id]);}
 undo(){this.lastMove=undefined;const d=this.undoStack.pop();if(d){this.redoStack.push(structuredClone(this.document));this.document=d;this.notice='Изменение отменено';}else this.notice='Нет изменений для отмены';}
 redo(){this.lastMove=undefined;const d=this.redoStack.pop();if(d){this.undoStack.push(structuredClone(this.document));this.document=d;this.notice='Изменение возвращено';}else this.notice='Нет изменений для возврата';}
 publish(){this.published=this.slide();this.notice='Слайд показан залу';}
 input(raw:string){
  // A literal prefix protects text containing the command marker.
  if(/^\s*дословно(?:\s|[:,.])/i.test(raw)){this.checkpoint();this.add('text',raw.replace(/^\s*дословно\s*[:,.]?\s*/i,''));this.notice='Добавлен дословный текст';return;}
  const phrases=raw.split(/[.!?]\s+(?=(?:команда|добавь|создай|выбери|перемести|сделай|первую|вторую|третью|под ним)(?:\s|[:,]))/i);
  if(phrases.length>1){for(const phrase of phrases)this.input(phrase);return;}
  const chunks=raw.split(/(?:^|\s)(команда)\s*[:,.]?\s*/i);
  if(chunks[0].trim()){
   const value=chunks[0].trim();
   if(/^(добавь|создай|выбери|перемести|сделай|удали|убери|замени|покажи|отмени|верни|первую|вторую|третью|четвертую|под ним|новый слайд|предыдущий слайд|следующий слайд)(?:\s|$)/i.test(value))this.command(value);
   else {this.checkpoint();if(this.selected&&['title','text','card'].includes(this.selected.kind))this.selected.text+=' '+value;else this.add('text',value);this.notice='Диктовка добавлена в выбранный компонент';}
  }
  for(let i=1;i<chunks.length;i+=2)this.command(chunks[i+1]??'');
 }
 command(raw:string){
  const original=raw.trim().replace(/[.!?]+$/,'');const c=original.toLowerCase().replace(/ё/g,'е');
  const cards=c.match(/^(?:под ним )?(?:добавь|создай) (две|три|четыре|[2-4]) карточки$/);
  if(cards){this.checkpoint();const count=Number(cards[1])||({'две':2,'три':3,'четыре':4}[cards[1]]??3);for(let i=0;i<count;i++){const item=this.add('card',`Карточка ${i+1}`);Object.assign(item,{x:64+i*1152/count,y:220,width:1152/count-24,height:280});}this.notice='Карточки добавлены';return;}
  const create=original.match(/^(?:добавь|создай) (заголовок|текст|карточку|фигуру|прямоугольник)(?:\s+(.+))?$/i);
  if(create){this.checkpoint();const kind=({'заголовок':'title','текст':'text','карточку':'card','фигуру':'shape','прямоугольник':'shape'} as const)[create[1].toLowerCase() as 'текст'];this.add(kind,(create[2]??'').replace(/^[«"“]|[»"”]$/g,''));this.notice='Компонент создан';return;}
  const ordinal=c.match(/(?:первую|вторую|третью|четвертую|первый|второй|третий|четвертый)/)?.[0];
  if(ordinal&&(/карточк/.test(c)||/^(первую|вторую|третью|четвертую|сделай)/.test(c))){const index=/перв/.test(ordinal)?0:/втор/.test(ordinal)?1:/трет/.test(ordinal)?2:3;const item=this.current.components.filter(x=>x.kind==='card')[index];if(!item){this.notice='Такой карточки нет';return;}this.select(item.id);const rename=original.match(/(?:назови|назвать|[—–])\s*[«"“]?(.+?)[»"”]?$/i);if(rename){this.checkpoint();item.text=rename[1];return;}}
  if(/^(отмени|отмена)$/.test(c)){this.undo();return;}
  if(/^(верни|повтори)$/.test(c)){this.redo();return;}
  if(/^(покажи|показать)( слайд)?( залу)?$/.test(c)){this.publish();return;}
  if(c==='новый слайд'){this.checkpoint();this.document.pages.push({...page(),background:this.color('background','#f7f5fa')});this.document.index=this.document.pages.length-1;this.document.selected=null;this.notice='Создан новый слайд';return;}
  if(/^(предыдущий|следующий) слайд$/.test(c)){const i=this.document.index+(c.startsWith('предыдущий')?-1:1);if(i<0||i>=this.document.pages.length){this.notice='В этой стороне больше нет слайдов';return;}this.document.index=i;this.document.selected=null;this.notice=`Слайд ${i+1}`;return;}
  const title=original.match(/^(?:заголовок|(?:замени|измени) заголовок(?: на)?)\s*[:,-]?\s+(.+)$/i);
  if(title&&!/^(крупнее|меньше|мельче|справа|слева|правее|левее)$/i.test(title[1])){this.checkpoint();const t=this.current.components.find(x=>x.kind==='title');if(t){t.text=title[1];this.document.selected=t.id;}else this.add('title',title[1]);this.notice='Заголовок изменён';return;}
  const image=original.match(/^добавь(?: справа| слева)? (?:изображение|картинку|фото)\s+(.+)$/i);
  if(image){this.checkpoint();const item=this.add('image',image[1]);if(c.includes('слева')){item.side='left';item.x=64;}this.notice='Добавлено место для изображения. Загрузите файл для выбранного компонента.';return;}
  const bullet=original.match(/^добавь (?:пункт|текст)\s*[:,-]?\s+(.+)$/i);
  if(bullet){this.checkpoint();this.add('text',bullet[1]);this.notice='Пункт добавлен';return;}
  const n=c.match(/^(?:выбери|убери|удали) (первый|второй|третий|четвертый|пятый|\d+) пункт$/);
  let target=this.selected;
  if(n){const num=Number(n[1])||['первый','второй','третий','четвертый','пятый'].indexOf(n[1])+1;target=this.current.components.filter(x=>x.kind==='text')[num-1];}
  else if(c.includes('заголов')&&!/это заголов/.test(c))target=this.current.components.find(x=>x.kind==='title');
  else if(/картинк|изображени|фото/.test(c)){const images=this.current.components.filter(x=>x.kind==='image');if(images.length!==1&&target?.kind!=='image'){this.notice='Выберите нужное изображение в списке компонентов';return;}target=target?.kind==='image'?target:images[0];}
  if(/^фон /.test(c)){const color=colors[c.slice(4)];if(!color){this.notice='Цвета: белый, чёрный, синий, красный, зелёный, фиолетовый';return;}this.checkpoint();this.current.background=color;this.notice='Фон изменён';return;}
  if(!target){this.notice='Сначала добавьте или выберите компонент';return;}
  if(c.startsWith('выбери ')){this.select(target.id);return;}
  const replace=original.match(/^замени (?:текст|это)(?: на)?\s*[:,-]?\s+(.+)$/i);
  const normalizedColor=c.replace(/красной|красным$/,'красный').replace(/синей|синим$/,'синий').replace(/фиолетовой|фиолетовым$/,'фиолетовый').replace(/белой|белым$/,'белый').replace(/черной|черным$/,'черный').replace(/зеленой|зеленым$/,'зеленый');
  const color=Object.entries(colors).find(([name])=>normalizedColor.endsWith(name));
  let edit:(()=>void)|undefined;
  if(/^(убери|удали)( выбранное| компонент| это)?$/.test(c)||n&&/^(убери|удали)/.test(c))edit=()=>{this.current.components=this.current.components.filter(x=>x.id!==target!.id);this.document.selected=null;};
  else if(/^(сделай это заголовком|это заголовок)$/.test(c))edit=()=>{for(const x of this.current.components)if(x.kind==='title'){x.kind='text';x.size=26;}target!.kind='title';target!.size=44;};
  else if(/^(сделай )?(последнюю мысль |это )?(отдельным )?пунктом$/.test(c))edit=()=>{target!.kind='text';target!.size=26;};
  else if(replace)edit=()=>{target!.text=replace[1];};
  else if(/(?:^| )крупнее$/.test(c))edit=()=>{target!.size=Math.min(72,target!.size+4);};
  else if(/(?:^| )(меньше|мельче)$/.test(c))edit=()=>{target!.size=Math.max(16,target!.size-4);};
  else if(/(?:^| )(справа|слева|правее|левее|выше|ниже|шире|уже|по центру)$/.test(c))edit=()=>{const t=target!;if(c.endsWith('выше'))t.y-=40;else if(c.endsWith('ниже'))t.y+=40;else if(c.endsWith('шире'))t.width+=60;else if(c.endsWith('уже'))t.width-=60;else if(c.endsWith('по центру'))t.x=(1280-t.width)/2;else {t.side=/справа|правее/.test(c)?'right':'left';t.x=c.endsWith('правее')?t.x+40:c.endsWith('левее')?t.x-40:t.side==='right'?1280-t.width-64:64;}this.update(t.id,{},false);};
  else if(color&&/цвет|сделай|покрась/.test(c))edit=()=>{if(target!.kind==='card'||target!.kind==='shape')target!.fill=color[1];else target!.color=color[1];};
  if(edit){this.checkpoint();edit();this.notice='Команда выполнена: '+original;}else this.notice='Команда не распознана: '+original;
 }
 setImage(url:string){if(this.selected?.kind!=='image')return;this.checkpoint();this.selected.url=url;this.notice='Изображение загружено';}
 slide():Slide{
  const elements=this.current.components;
  const html=`<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;font-family:Arial"><main style="position:relative;width:100vw;height:56.25vw;background:${this.current.background};overflow:hidden">${elements.map(x=>`<div style="position:absolute;box-sizing:border-box;font-family:${escape((x.font??'Arial').replace(/[^\p{L}\p{N} -]/gu,''))};left:${x.x/12.8}%;top:${x.y/7.2}%;width:${x.width/12.8}%;height:${x.height/7.2}%;background:${x.kind==='chart'?'transparent':x.fill};color:${x.color};font-size:${x.size/12.8}vw;font-weight:${(x.bold??(x.kind==='title'))?700:400};font-style:${x.italic?'italic':'normal'};text-align:${x.align??'left'};transform:rotate(${x.rotation??0}deg);opacity:${x.opacity??1};border-radius:${(x.radius??0)/12.8}vw;border:${(x.borderWidth??0)/12.8}vw solid ${x.borderColor??'transparent'};padding:${x.kind==='card'?1.25:0}vw;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere">${contentHtml(x)}</div>`).join('')}</main></body></html>`;
  const background=this.current.backgroundUrl?`<img alt="" src="${escape(mediaUrl(this.current.backgroundUrl))}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"/>`:'';
  return {chunk_id:this.current.id,rev:++this.revision,title:elements.find(x=>x.kind==='title')?.text??null,bullets:elements.filter(x=>x.kind==='text').map(x=>x.text),notes:[this.current.notes??'',...elements.map(x=>x.attribution??'')].filter(Boolean).join('\n'),source:'voice-editor',html:background?html.replace(/(<main\b[^>]*>)/,'$1'+background):html};
 }
}

