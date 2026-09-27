import {it,expect} from 'vitest';
import {parseDeckVoice} from './deckVoice';

it.each(['Выбери первый элемент','Выдели первый объект','Покажи элемент номер один','Выбери объект один'])( '%s',text=>{
  expect(parseDeckVoice(text)).toEqual({kind:'element',number:1});
});
it('keeps slide selection and dictated text separate',()=>{
  expect(parseDeckVoice('Выбери первый слайд')).toEqual({kind:'select',number:1});
  expect(parseDeckVoice('Напиши первый элемент')).toEqual({kind:'text',text:'первый элемент'});
});
