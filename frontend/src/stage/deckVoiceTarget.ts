import type {Scene} from '../designer/api';
import {deckNumber} from './deckVoiceExtended';
import {deckSelectable} from './deckVoiceExecutor';
import {normalizeVoice} from './voiceVocabulary';
const isTitle=(role:string)=>/^(?:title|heading|заголовок)$/i.test(role);

export function deckRewriteTarget(instruction:string,scenes:Scene[],index:number,selectedId:string|null,explicitSlide?:number):{slide:number;id:string}|{notice:string}{
 const c=normalizeVoice(instruction).replace(/[.!?]+$/,'');
 let slide=explicitSlide??index+1;
 const suffix=c.match(/\s+на (?:слайде (.+)|(.+) слайде)$/);
 let command=c;
 if(suffix){const n=deckNumber(suffix[1]??suffix[2]);if(n===undefined||explicitSlide!==undefined&&n!==explicitSlide)return {notice:'Уточните номер слайда'};slide=n;command=c.slice(0,suffix.index);}
 if(/слайд/.test(command))return {notice:'Уточните номер слайда отдельной командой'};
 const scene=scenes[slide-1];if(!Number.isInteger(slide)||slide<1||!scene)return {notice:`Слайда ${slide} нет`};
 const verb='(?:сократи|перепиши|измени|сделай|перефразируй|переведи|упрости|увеличь|уменьши)';
 const role=command.match(new RegExp(`^${verb} ((?:этот |выбранный )?текст заголовка|(?:этот |выбранный )?заголовок|(?:этот |выбранный )?текст)(?: (.*))?$`));
 const title=!!role&&/заголов/.test(role[1]);
 const selected=!!role&&!title;
 const qualifier=role?.[2]??'';
 const number=command.match(new RegExp(`^${verb} (?:текст )?(?:элемент|объект)(?:а)? (?:номер )?(.+?)(?:[,;:]|$)`));
 let element;
 if(number){const n=deckNumber(number[1]);if(n===undefined||n<1)return {notice:'Уточните номер элемента'};element=deckSelectable(scene)[n-1];}
 else if(role&&(/^(?:номер |№|\d|[«"“])/.test(qualifier)||deckNumber(qualifier)!==undefined||deckNumber(qualifier.split(' ')[0])!==undefined)){
  const name=qualifier.match(/^[«"“]([^»"”]+)[»"”](?: |$)/);
  if(name){const found=scene.elements.filter(e=>e.type==='text'&&normalizeVoice(e.text)===name[1]&&(!title||isTitle(e.role)));if(found.length!==1)return {notice:'Указанный текст не найден однозначно'};element=found[0];}
  else {const n=deckNumber(qualifier.replace(/^(?:номер |№\s*)/,''));if(n===undefined||n<1)return {notice:'Уточните номер элемента'};element=deckSelectable(scene)[n-1];if(title&&element&&!isTitle(element.role))return {notice:'Указанный элемент не является заголовком'};}
 }
 else if(title){const found=scene.elements.filter(e=>e.type==='text'&&isTitle(e.role));if(found.length!==1)return {notice:'Уточните номер заголовка'};element=found[0];}
 else if(selected||!/(?:заголов|элемент|объект|карточ|таблиц|диаграмм|изображени)/.test(command))element=scene.elements.find(e=>e.id===selectedId);
 else return {notice:'Уточните объект отдельной командой выбора'};
 return element?.type==='text'?{slide,id:element.id}:{notice:'Текстовый элемент не найден'};
}
