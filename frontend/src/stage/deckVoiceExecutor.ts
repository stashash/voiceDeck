import {deckElementAction,moveDeckElement,patchSlideText,patchNotes,revertVariant,setSlidePattern,slidesAction} from '../designer/api';
import type {DeckVariantState,Scene,SlidePatternOption} from '../designer/api';
import type {DeckVoiceAction} from './deckVoice';

export const deckSelectable=(scene:Scene)=>[...scene.elements.filter(e=>e.type==='text'),...scene.elements.filter(e=>e.type!=='text')];
export type DeckVoiceContext={deckId:string;variant:string;scenes:Scene[];index:number;selectedId:string|null;patterns?:SlidePatternOption[]};
export type DeckVoiceResult={index?:number;selectedId?:string|null;notice?:string;dictate?:{slide:number;id:string};confirmDelete?:number;state?:DeckVariantState;movement?:{dx:number;dy:number;align?:'left'|'right'|'top'|'bottom'|'center'}};

/** The same executor is used by microphone commands, the command field and audio acceptance. */
export async function executeDeckVoice(a:DeckVoiceAction,c:DeckVoiceContext):Promise<DeckVoiceResult>{
 const {deckId,variant,scenes}=c;
 const invalid=(notice:string):DeckVoiceResult=>({notice});
 if(a.kind==='unknown')return invalid('Команда не распознана. Документ не изменён.');
 if(a.kind==='deselect')return {selectedId:null,notice:'Выделение снято'};
 if(a.kind==='next'||a.kind==='previous'||a.kind==='select'){
  const index=a.kind==='select'?a.number-1:c.index+(a.kind==='next'?1:-1);
  return Number.isInteger(index)&&index>=0&&index<scenes.length?{index,selectedId:null,notice:`Слайд ${index+1} из ${scenes.length}`} : invalid(`В презентации ${scenes.length} слайдов`);
 }
 const n=a.slide??c.index+1,scene=scenes[n-1];
 if(!Number.isInteger(n)||n<1||!scene)return invalid(`Слайда ${n} нет`);
 const result:DeckVoiceResult={...(a.slide!==undefined?{index:n-1}:{}),notice:'Правка сохранена'};
 const elements=deckSelectable(scene);
 const el=a.elementNumber!==undefined?elements[a.elementNumber-1]:scene.elements.find(e=>e.id===c.selectedId);
 if(a.elementNumber!==undefined&&(!Number.isInteger(a.elementNumber)||a.elementNumber<1||!el))return invalid(`Элемента ${a.elementNumber} нет`);
 if(a.kind==='element'||a.kind==='title'){
  const titles=elements.filter(e=>e.type==='text'&&/^(?:title|heading|заголовок)$/i.test(e.role));
  if(a.kind==='title'&&titles.length!==1)return invalid('Уточните номер заголовка');
  const selected=a.kind==='title'?titles[0]:elements[a.number-1];
  return selected?{...result,selectedId:selected.id,notice:`Выбран элемент ${elements.indexOf(selected)+1}`} : invalid('Элемент не найден');
 }
 if(['style','move','deleteElement','duplicateElement','layer','table','text','appendText','textStart'].includes(a.kind)&&!el)return invalid('Объект не выбран');
 if(a.elementNumber!==undefined)result.selectedId=el!.id;
 if(a.kind==='text'||a.kind==='appendText'||a.kind==='textStart'){
  if(el!.type!=='text')return invalid('Выбранный объект не является текстом');
  if(a.kind==='textStart')return {...result,selectedId:el!.id,dictate:{slide:n,id:el!.id},notice:'Ожидается текст'};
  result.state=await patchSlideText(deckId,variant,n,el!.id,a.kind==='appendText'?`${el!.text.trimEnd()} ${a.text}`.trimStart():a.text);
 }else if(a.kind==='style'){
  const {kind:_,slide:__,elementNumber:___,...props}=a;
  result.state=await deckElementAction(deckId,variant,n,{...props,action:'style',element_id:el!.id});
 }else if(a.kind==='background')result.state=await deckElementAction(deckId,variant,n,{action:'background',color:a.color});
 else if(a.kind==='notes')result.state=await patchNotes(deckId,variant,n,a.text);
 else if(a.kind==='layer')result.state=await deckElementAction(deckId,variant,n,{action:'z_order',element_id:el!.id,order:a.order});
 else if(a.kind==='table')result.state=await deckElementAction(deckId,variant,n,{action:a.action,element_id:el!.id,row:a.row,column:a.column,text:a.text});
 else if(a.kind==='move'){
  result.state=await moveDeckElement(deckId,variant,n,el!.id,a.dx,a.dy,a.align);
  result.movement={dx:a.dx,dy:a.dy,align:a.align};
 }else if(a.kind==='deleteElement'||a.kind==='duplicateElement'){
  result.state=await deckElementAction(deckId,variant,n,{action:a.kind==='deleteElement'?'delete':'duplicate',element_id:el!.id});
  result.selectedId=a.kind==='deleteElement'?null:result.state.scenes[n-1].elements.at(-1)!.id;
 }else if(a.kind==='addElement'){
  const type=a.elementType??'text';
  if(type==='image'||type==='chart')return invalid('Прямое добавление этого объекта здесь недоступно');
  result.state=await deckElementAction(deckId,variant,n,{action:'add',element_type:type,...(type==='text'||type==='title'||type==='card'?{text:a.text}:{}),table:a.table});
  result.selectedId=result.state.scenes[n-1].elements.at(-1)!.id;
 }else if(a.kind==='delete')return {...result,confirmDelete:n,notice:`Удалить слайд ${n}?`};
 else if(a.kind==='undo')result.state=await revertVariant(deckId,variant);
 else if(a.kind==='pattern'){
  const pattern=c.patterns?.[a.number-1];if(!pattern)return invalid('Образец не найден');
  result.state=await setSlidePattern(deckId,variant,n,pattern.pattern_id);result.selectedId=null;
 }else if(a.kind==='slideMove'){
  if(a.number<1||a.number>scenes.length)return invalid('Такой позиции слайда нет');
  result.state=await slidesAction(deckId,variant,{action:'move',index:n,to:a.number});result.index=a.number-1;
 }else if(a.kind==='add'||a.kind==='copy'){
  result.state=await slidesAction(deckId,variant,{action:a.kind,index:n});result.index=n;result.selectedId=null;
 }else return invalid('Команда требует отдельного режима');
 return result;
}
