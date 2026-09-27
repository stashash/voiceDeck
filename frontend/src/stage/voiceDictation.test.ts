import {expect,it} from 'vitest';
import {editDictation} from './voiceDictation';
it('accumulates phrases and preserves literal commands',()=>{
 expect(editDictation('План запуска.','Вторая фраза.')).toEqual({kind:'draft',text:'План запуска. Вторая фраза.'});
 expect(editDictation('','буквально Готово')).toEqual({kind:'draft',text:'Готово'});
 expect(editDictation('','буквально Стоп')).toEqual({kind:'draft',text:'Стоп'});
 expect(editDictation('текст','Готово.')).toEqual({kind:'finish'});
 expect(editDictation('текст','Отмена диктовки')).toEqual({kind:'cancel'});
});
it('allows paragraphs and local word correction without a model',()=>{
 expect(editDictation('Первый','Новый абзац')).toEqual({kind:'draft',text:'Первый\n\n'});
 expect(editDictation('Первый\n\n','Второй')).toEqual({kind:'draft',text:'Первый\n\nВторой'});
 expect(editDictation('План проекта','Исправь последнее слово на запуска')).toEqual({kind:'draft',text:'План запуска'});
 expect(editDictation('План запуска','Удали последнее слово')).toEqual({kind:'draft',text:'План'});
});
