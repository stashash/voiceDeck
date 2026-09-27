import {expect,it} from 'vitest';
import {deckRewriteTarget} from './deckVoiceTarget';
import type {Scene} from '../designer/api';
const scenes:Scene[]=[{slide_id:'s1',pattern_id:'p1',theme:'light',variant:'a',elements:[
 {id:'title',type:'text',role:'title',box:[0,0,.5,.2],text:'Title'},
 {id:'body',type:'text',role:'body',box:[0,.3,.5,.2],text:'Body'},
]}];
it.each([
 ['Сократи заголовок',{slide:1,id:'title'}],
 ['Сократи текст заголовка',{slide:1,id:'title'}],
 ['Перепиши выбранный текст без заголовка',{slide:1,id:'body'}],
 ['Перефразируй этот текст',{slide:1,id:'body'}],
 ['Сократи элемент два',{slide:1,id:'body'}],
 ['Сократи заголовок на первом слайде',{slide:1,id:'title'}],
])('resolves exact rewrite target: %s',(phrase,expected)=>expect(deckRewriteTarget(phrase as string,scenes,0,'body')).toEqual(expected));
it.each(['Сократи заголовок на слайде 99','Сократи заголовок на слайде 0','Сократи заголовок на слайде неизвестно','Сократи элемент 99','Сделай карточку короче','Перепиши заголовки на всех слайдах','Сократи заголовок номер 99','Сократи заголовок «Несуществующий»','Сократи текст «Несуществующий»'])('rejects unresolved or nonexistent scope: %s',phrase=>expect(deckRewriteTarget(phrase,scenes,0,'body')).toHaveProperty('notice'));
it('rejects conflicting scopes',()=>expect(deckRewriteTarget('Сократи заголовок на слайде два',scenes,0,'body',1)).toHaveProperty('notice'));
it('rejects ambiguous title roles',()=>{const duplicate=structuredClone(scenes);duplicate[0].elements[1].role='title';expect(deckRewriteTarget('Сократи заголовок',duplicate,0,'body')).toHaveProperty('notice');});
it('resolves explicit literal name strictly',()=>expect(deckRewriteTarget('Сократи текст «Title»',scenes,0,'body')).toEqual({slide:1,id:'title'}));
it('resolves spoken numbers before selection fallback',()=>{expect(deckRewriteTarget('Сократи текст два',scenes,0,'title')).toEqual({slide:1,id:'body'});expect(deckRewriteTarget('Сократи заголовок девяносто девять',scenes,0,'title')).toHaveProperty('notice');});
it('distinguishes title from subtitle',()=>{const fixture=structuredClone(scenes);fixture[0].elements[1].role='subtitle';expect(deckRewriteTarget('Сократи заголовок',fixture,0,'body')).toEqual({slide:1,id:'title'});expect(deckRewriteTarget('Сократи заголовок номер 2',fixture,0,'body')).toHaveProperty('notice');});
