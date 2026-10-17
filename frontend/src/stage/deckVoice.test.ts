import {it,expect} from 'vitest';
import {parseDeckVoice} from './deckVoice';
it.each([
 ['Измени текст. Один, два, три.',{kind:'text',text:'Один, два, три.'}],
 ['Один. Измени текст. Раз, два, три. Пока все',{kind:'text',text:'Раз, два, три. Пока все',elementNumber:1}],
 ['Выбери элемент два. Поменяй текст: Новый текст',{kind:'text',text:'Новый текст',elementNumber:2}],
 ['Замени текст, новый заголовок',{kind:'text',text:'новый заголовок'}],
])('handles ASR sentence boundaries in text replacement: %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));
it.each([
 ['Ещё',{kind:'repeat',factor:1}],
 ['Ещё немного',{kind:'repeat',factor:.25}],
 ['Теперь чуть вверх',{kind:'move',dx:0,dy:-5/720}],
 ['Удали элемент',{kind:'deleteElement'}],
 ['Скопируй его',{kind:'duplicateElement'}],
 ['Сделай крупнее',{kind:'style',scale:1.15}],
 ['Размер шрифта двадцать четыре',{kind:'style',size_pt:24}],
])('understands contextual edits: %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));
it.each([
 ['вправо',{kind:'move',dx:20/1280,dy:0}],
 ['перемести элемент влево на 40',{kind:'move',dx:-40/1280,dy:0}],
 ['вниз на двадцать пикселей',{kind:'move',dx:0,dy:20/720}],
 ['в центр',{kind:'move',dx:0,dy:0,align:'center'}],
 ['следующий слайд',{kind:'next'}],
])('moves without invoking a model: %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));
it('routes commands without a model',()=>{
 expect(parseDeckVoice('Выбери элемент два.')).toEqual({kind:'element',number:2});
 expect(parseDeckVoice('Слайд 3')).toEqual({kind:'select',number:3});
 expect(parseDeckVoice('Выбери образец один')).toEqual({kind:'pattern',number:1});
 expect(parseDeckVoice('Замени текст на Рост 20%')).toEqual({kind:'text',text:'Рост 20%'});
 expect(parseDeckVoice('Удали слайд')).toEqual({kind:'delete'});
 expect(parseDeckVoice('Сократи заголовок')).toEqual({kind:'ask',text:'Сократи заголовок'});
 expect(parseDeckVoice('перейди вперёд')).toEqual({kind:'next'});
 expect(parseDeckVoice('назад')).toEqual({kind:'previous'});
 expect(parseDeckVoice('перейди к слайду два')).toEqual({kind:'select',number:2});
 expect(parseDeckVoice('создай слайд')).toEqual({kind:'add'});
 expect(parseDeckVoice('выбери один')).toEqual({kind:'element',number:1});
 expect(parseDeckVoice('покажи 3')).toEqual({kind:'element',number:3});
 expect(parseDeckVoice('добавь заголовок План запуска')).toEqual({kind:'addElement',elementType:'title',text:'План запуска'});
 expect(parseDeckVoice('на слайде 3 добавь текст Результат')).toEqual({kind:'addElement',elementType:'text',text:'Результат',slide:3});
});
it.each([
 ['Выбери один',{kind:'element',number:1}],
 ['Один',{kind:'element',number:1}],
 ['Два',{kind:'element',number:2}],
 ['Выбери заголовок.',{kind:'title'}],
 ['Выбери первый слайд',{kind:'select',number:1}],
 ['На первом слайде.',{kind:'select',number:1}],
 ['На слайде один выбери заголовок',{kind:'title',slide:1}],
 ['На втором слайде выбери два',{kind:'element',number:2,slide:2}],
 ['Слайд пятнадцать',{kind:'select',number:15}],
 ['Выбери что-нибудь',{kind:'unknown',text:'Выбери что-нибудь'}],
 ['Сегодня хорошая погода',{kind:'unknown',text:'Сегодня хорошая погода'}],
])('recognizes recorded phrase %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));
it.each([
 ['Измени текст',{kind:'textStart'}],
 ['Меняй текст на любой',{kind:'text',text:'любой'}],
 ['Выбери два, поменяй текст на любой.',{kind:'text',text:'любой.',elementNumber:2}],
 ['Ставь текст. Развитие искусственного интеллекта',{kind:'text',text:'Развитие искусственного интеллекта'}],
 ['Измени текст, добавь в конце слова «привет»',{kind:'appendText',text:'привет'}],
 ['Замени текст на Рост 20%.',{kind:'text',text:'Рост 20%.'}],
])('edits text for recorded phrase %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));

import {replacementText} from './deckVoiceExecutor';
it('dictated replacement starts with a capital and keeps a period only where the old text had one',()=>{
 expect(replacementText('отчёты готовы к началу рабочего дня.','Отчёты готовы на 2,5 часа раньше')).toBe('Отчёты готовы к началу рабочего дня');
 expect(replacementText('данные приходят утром.','Данные доступны к началу дня.')).toBe('Данные приходят утром.');
 expect(replacementText('и так далее...','Заголовок')).toBe('И так далее...');
});
it('dictated replacement drops quotes and an ASR capital around the whole text',()=>{
 expect(replacementText('«отчёты Готовы к началу рабочего дня».','Отчёты готовы на 2,5 часа раньше')).toBe('Отчёты готовы к началу рабочего дня');
 expect(replacementText('отчёты Готовы к началу рабочего дня»','Отчёты готовы')).toBe('Отчёты готовы к началу рабочего дня');
 expect(replacementText('запуск проекта «Альфа»','Заголовок')).toBe('Запуск проекта «Альфа»');
 expect(replacementText('"итоги квартала".','Заголовок')).toBe('Итоги квартала');
 expect(replacementText('Итоги пилота в Москве','Заголовок')).toBe('Итоги пилота в Москве');
});
it('style commands accept the infinitive the recognizer often hears',()=>{
 expect(parseDeckVoice('Сделать текст синим.')).toEqual({kind:'style',color:'2563EB'});
 expect(parseDeckVoice('сделать текст крупнее')).toEqual({kind:'style',scale:1.15});
});
