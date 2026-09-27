import {expect,it} from 'vitest';
import {parseDeckVoice} from './deckVoice';
it.each([
 ['Ячейка два один: API v2.',{kind:'table',action:'table_cell',row:1,column:1,text:'API v2.'}],
 ['Удали строку два',{kind:'table',action:'table_row_delete',row:1}],
 ['Добавь строку два',{kind:'table',action:'table_row_add',row:1}],
 ['Сделай текст жирным.',{kind:'style',bold:true}],
 ['Убери курсив',{kind:'style',italic:false}],
 ['Ширина двести пятьдесят',{kind:'style',width:250/1280}],
 ['Фон слайда белый',{kind:'background',color:'FFFFFF'}],
 ['На передний план',{kind:'layer',order:'front'}],
 ['Заметки докладчика API v2.',{kind:'notes',text:'API v2.'}],
 ['Выбери элемент два. Сделай текст жирным',{kind:'style',bold:true,elementNumber:2}],
])('compiles deterministic command: %s',(phrase,expected)=>expect(parseDeckVoice(phrase as string)).toEqual(expected));
it.each(['Удали строку один','Добавь строку один','Ширина минус пять','Размер шрифта пятьсот','Добавь таблицу сто на два'])('rejects invalid operation: %s',phrase=>expect(parseDeckVoice(phrase).kind).toBe('unknown'));
