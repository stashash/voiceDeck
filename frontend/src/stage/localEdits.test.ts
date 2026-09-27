import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {localEdits} from './localEdits';
beforeEach(()=>{vi.stubGlobal('localStorage',{setItem:vi.fn()});vi.stubGlobal('fetch',vi.fn(()=>{throw Error('Unexpected model call');}));});
afterEach(()=>vi.unstubAllGlobals());
it('handles everyday Russian editing commands entirely offline',async()=>{
 const e=new VoiceEditor(),title=e.add('title','План'),a=e.add('card','Продажи'),b=e.add('card','Продукт');
 const say=(s:string)=>e.interpret(s,()=>{});
 await say('Выбери заголовок.');expect(e.selected?.id).toBe(title.id);
 await say('Сделай заголовок красным');expect(title.color).toBe('#dc2626');
 await say('Сделай заголовок крупнее');expect(title.size).toBe(48);
 await say('Сделай его жирным');expect(title.bold).toBe(true);
 await say('Размер текста тридцать два');expect(title.size).toBe(32);
 await say('Выбери вторую карточку');expect(e.selected?.id).toBe(b.id);
 await say('Перемести первую карточку вправо на тридцать');expect(a.x).toBe(94);
 await say('Подвинь карточку «Продажи» на двадцать пикселей вниз');expect(a.y).toBe(200);
 await say('Переименуй карточку «Продажи» в «Рост»');expect(a.text).toBe('Рост');
 await say('Замени заголовок на «Запуск и рост»');expect(title.text).toBe('Запуск и рост');
 await say('Сделай фон белым');expect(e.current.background).toBe('#ffffff');
 await say('Удали карточку «Рост»');expect(e.current.components.map(c=>c.id)).not.toContain(a.id);
 await say('Отмена');expect(e.current.components.map(c=>c.id)).toContain(a.id);
 await say('Добавь новый слайд');expect(e.document.index).toBe(1);
 await say('Перейди на первый слайд');expect(e.document.index).toBe(0);
 expect(fetch).not.toHaveBeenCalled();
});
it('refuses ambiguous and locked targets without touching an unrelated selection',async()=>{
 const e=new VoiceEditor();e.add('title','One');e.add('title','Two');e.add('card','Card');
 await expect(e.interpret('Сделай заголовок красным',()=>{})).rejects.toThrow('несколько');
 expect(e.selected?.text).toBe('Card');
 e.selected!.locked=true;
 await expect(e.interpret('Сделай карточку шире',()=>{})).rejects.toThrow('заблокирован');
 await e.interpret('Разблокируй карточку',()=>{});expect(e.selected?.locked).toBe(false);
 expect(fetch).not.toHaveBeenCalled();
});
it('never consumes the recognized prefix of a compound editing request',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({operations:[],clarification:'Уточните',summary:''})}));
 const e=new VoiceEditor();const title=e.add('title','Plan');
 await e.interpret('Сделай заголовок крупнее и красным',()=>{});
 expect(title.size).toBe(44);expect(fetch).toHaveBeenCalledOnce();
});

it.each([
 ['Размер шрифта тридцать два','size',32],
 ['Шрифт сорок восемь','size',48],
 ['Установи размер шрифта заголовка на тридцать два пункта','size',32],
 ['Размер текста номер один сто двадцать восемь','size',128],
 ['Ширина заголовка триста двадцать пикселей','width',320],
 ['Сделай ширину заголовка тысяча двести восемьдесят','width',1280],
 ['Высота заголовка двести сорок','height',240],
 ['Поворот заголовка минус тридцать градусов','rotation',-30],
 ['Непрозрачность заголовка семьдесят пять процентов','opacity',.75],
 ['Скругление заголовка двадцать четыре','radius',24],
] as const)('parses the complete spoken numeric operand: %s',async(command,key,value)=>{
 const e=new VoiceEditor(),title=e.add('title','План');
 await e.interpret(command,()=>{});
 expect(e.current.components[0][key]).toBe(value);expect(e.undoStack).toHaveLength(1);
 const saved=JSON.parse(vi.mocked(localStorage.setItem).mock.calls.at(-1)![1]);
 expect(saved.pages[0].components[0][key]).toBe(value);
 e.undo();expect(e.current.components[0][key]).not.toBe(value);
 expect(e.selected?.id).toBe(title.id);expect(fetch).not.toHaveBeenCalled();
});

it('keeps numbers and command words inside a quoted target name',async()=>{
 const e=new VoiceEditor(),target=e.add('card','Сто двадцать и Удали слайд');
 const other=e.add('card','Выбранная');
 await e.interpret('Ширина карточки «Сто двадцать и Удали слайд» четыреста двадцать',()=>{});
 expect(target.width).toBe(420);expect(other.width).toBe(320);
 expect(e.selected?.id).toBe(other.id);expect(fetch).not.toHaveBeenCalled();
});

it('resolves a complete numeric target list before changing any font size',async()=>{
 const e=new VoiceEditor(),a=e.add('card','A'),b=e.add('card','B');
 await e.interpret('Размер шрифта номера один и два тридцать два',()=>{});
 expect([a.size,b.size]).toEqual([32,32]);expect(e.undoStack).toHaveLength(1);
 e.undo();expect(e.current.components.map(c=>c.size)).toEqual([26,26]);
 const before=structuredClone(e.document);
 await expect(e.interpret('Размер шрифта номера один и девять тридцать два',()=>{})).rejects.toThrow('Такого номера нет');
 expect(e.document).toEqual(before);expect(e.undoStack).toHaveLength(0);
 e.current.components[1].locked=true;const locked=structuredClone(e.document);
 await expect(e.interpret('Размер шрифта номера один и два тридцать два',()=>{})).rejects.toThrow('заблокирован');
 expect(e.document).toEqual(locked);expect(e.undoStack).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});

it.each([
 'Размер шрифта ноль',
 'Размер текста сто шестьдесят один',
 'Ширина минус двадцать',
 'Высота семьсот двадцать один',
 'Непрозрачность сто один',
 'Размер текста номер девять тридцать два',
 'Размер текста карточки «Нет такой» тридцать два',
 'Размер текста название-ошибка тридцать два',
 'Размер текста сто сто',
 'Размер текста двадцать ноль',
 'Сделай карточку «Нет такой» полужирной',
 'Сделай карточку Пропавшая жирным',
 'Сделай «Нет такой» жирным',
 'Выключи курсив у номер девять',
 'Выровняй номер девять по правому краю',
 'Перемести карточку «Нет такой» на передний план',
])('rejects invalid operands or explicit targets without fallback: %s',async command=>{
 const e=new VoiceEditor();e.add('card','Выбранная');const before=structuredClone(e.document);
 await expect(e.interpret(command,()=>{})).rejects.toThrow();
 expect(e.document).toEqual(before);expect(e.undoStack).toHaveLength(0);
 expect(fetch).not.toHaveBeenCalled();expect(localStorage.setItem).not.toHaveBeenCalled();
});

it('applies positive and negative font styles independently and undoes the last style',async()=>{
 const e=new VoiceEditor(),title=e.add('title','План');const other=e.add('card','Другая');
 for(const command of ['Сделай заголовок полужирным','Включи курсив у заголовка','Выключи жирный шрифт у заголовка'])await e.interpret(command,()=>{});
 expect(title).toMatchObject({bold:false,italic:true});expect(other.bold).toBeUndefined();
 await e.interpret('Сделай заголовок без курсива',()=>{});expect(title.italic).toBe(false);
 e.undo();expect(e.current.components[0]).toMatchObject({bold:false,italic:true});
 await e.interpret('Сделай заголовок не жирным',()=>{});
 expect(e.current.components[0].bold).toBe(false);expect(fetch).not.toHaveBeenCalled();
});

it('distinguishes text alignment from component geometry and distributes vertically',async()=>{
 const e=new VoiceEditor(),title=e.add('title','План');
 await e.interpret('Выровняй текст по правому краю',()=>{});
 expect(title.align).toBe('right');expect(title.x).toBe(64);
 await e.interpret('Выровняй заголовок по левому краю',()=>{});expect(title.x).toBe(0);
 await e.interpret('Выровняй текст заголовка по центру',()=>{});expect(title.align).toBe('center');expect(title.x).toBe(0);
 const a=e.add('card','A'),b=e.add('card','B'),c=e.add('card','C');
 a.y=20;b.y=100;c.y=620;a.height=b.height=c.height=40;e.selectMany([a.id,b.id,c.id]);
 await e.interpret('Распредели по вертикали',()=>{});
 expect([a.y,b.y,c.y]).toEqual([20,320,620]);expect(fetch).not.toHaveBeenCalled();
});

it('changes z order by stable explicit target, retaining selection and undo',async()=>{
 const e=new VoiceEditor(),a=e.add('card','A'),b=e.add('card','B'),c=e.add('card','C');
 await e.interpret('Перемести первую карточку на передний план',()=>{});
 expect(e.current.components.map(c=>c.id)).toEqual([b.id,c.id,a.id]);expect(e.selected?.id).toBe(c.id);
 await e.interpret('Опусти номер один на слой ниже',()=>{});
 expect(e.current.components.map(c=>c.id)).toEqual([b.id,a.id,c.id]);
 await e.interpret('Отправь номер три на задний план',()=>{});
 expect(e.current.components.map(c=>c.id)).toEqual([c.id,b.id,a.id]);
 e.undo();expect(e.current.components.map(c=>c.id)).toEqual([b.id,a.id,c.id]);
 expect(e.current.components.find(c=>c.id===a.id)?.voiceNumber).toBe(1);expect(fetch).not.toHaveBeenCalled();
});

it('edits spoken table coordinates and ordinal rows and columns on explicit tables',async()=>{
 const e=new VoiceEditor(),table=e.add('table','План');
 table.rows=[['A','B'],['C','D'],['E','F']];const other=e.add('table','Другая');other.rows=[['Без изменений']];
 await e.interpret('В таблице «План» ячейка строка два столбец один: «Рост, Ёж! И Удали слайд.»',()=>{});
 expect(table.rows[1][0]).toBe('Рост, Ёж! И Удали слайд.');expect(e.document.pages).toHaveLength(1);
 await e.interpret('Удали вторую строку из таблицы «План»',()=>{});expect(table.rows).toEqual([['A','B'],['E','F']]);
 await e.interpret('Вставь третью строку в таблицу номер один',()=>{});expect(table.rows[2]).toEqual(['','']);
 await e.interpret('Добавь столбец в таблицу номер один',()=>{});expect(table.rows[0]).toEqual(['A','B','']);
 await e.interpret('Удали столбец два из таблицы «План»',()=>{});expect(table.rows[0]).toEqual(['A','']);
 expect(other.rows).toEqual([['Без изменений']]);expect(e.selected?.id).toBe(other.id);
 e.undo();expect(e.current.components[0].rows?.[0]).toEqual(['A','B','']);expect(fetch).not.toHaveBeenCalled();
});

it('preserves cell and renamed text literally without splitting quoted commands',()=>{
 const e=new VoiceEditor(),table=e.add('table','План');table.rows=[['']];
 expect(localEdits(e,'Ячейка один, один: Выручка, Ёж! Удали строку один.')).toBe(true);
 expect(table.rows).toEqual([['Выручка, Ёж! Удали строку один.']]);
 const title=e.add('title','План');
 expect(localEdits(e,'Переименуй заголовок в “API, Ёж! И Удали слайд.”')).toBe(true);
 expect(title.text).toBe('API, Ёж! И Удали слайд.');expect(e.document.pages).toHaveLength(1);
 expect(localEdits(e,'Переименуй заголовок в API, Ёж!')).toBe(true);
 expect(title.text).toBe('API, Ёж!');expect(fetch).not.toHaveBeenCalled();
});

it('resolves the full title reference before changing text on another selection',async()=>{
 const e=new VoiceEditor(),title=e.add('title','План'),other=e.add('card','Другая');
 await e.interpret('Замени текст заголовка на Готово',()=>{});
 expect(title.text).toBe('Готово');expect(other.text).toBe('Другая');expect(e.selected?.id).toBe(other.id);
 e.current.components=e.current.components.filter(c=>c.id!==title.id);const before=structuredClone(e.document);
 await expect(e.interpret('Замени текст заголовка на Ошибка',()=>{})).rejects.toThrow('Такого объекта нет');
 expect(e.document).toEqual(before);expect(fetch).not.toHaveBeenCalled();
});

it('does not treat a rename delimiter inside quoted names as the new text boundary',async()=>{
 const e=new VoiceEditor(),target=e.add('card','Один в два'),other=e.add('card','Другая');
 await e.interpret('Переименуй карточку «Один в два» в «API: Удали слайд. Затем Выдели всё!»',()=>{});
 expect(target.text).toBe('API: Удали слайд. Затем Выдели всё!');expect(other.text).toBe('Другая');
 expect(e.document.pages).toHaveLength(1);expect(fetch).not.toHaveBeenCalled();
});

it.each([
 'Ячейка ноль, один: Ошибка',
 'Ячейка два, один: Ошибка',
 'Ячейка один, три: Ошибка',
 'Ячейка двадцать один два: Ошибка',
 'Ячейка минус один, один: Ошибка',
 'Ячейка один и два: Ошибка',
 'Удали строку ноль',
 'Удали строку два',
 'Удали строку один',
 'Добавь столбец четыре',
 'Удали столбец ноль',
 'Удали строку два из таблицы «Нет такой»',
 'В таблице номер девять ячейка один, один: Ошибка',
])('rejects invalid table addresses atomically: %s',async command=>{
 const e=new VoiceEditor(),table=e.add('table','План');table.rows=[['A','B']];const before=structuredClone(e.document);
 await expect(e.interpret(command,()=>{})).rejects.toThrow();
 expect(e.document).toEqual(before);expect(e.undoStack).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});

it('keeps table type and lock validation in the operation executor',async()=>{
 const e=new VoiceEditor();e.add('card','Выбранная');let before=structuredClone(e.document);
 await expect(e.interpret('Ячейка один, один: X',()=>{})).rejects.toThrow('таблицу');expect(e.document).toEqual(before);
 const table=e.add('table','План');table.rows=[['A','B']];table.locked=true;before=structuredClone(e.document);
 await expect(e.interpret('Удали столбец два',()=>{})).rejects.toThrow('заблокирован');expect(e.document).toEqual(before);
 expect(e.undoStack).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});

it('leaves free form slide design and compound edits for planning without partial mutation',()=>{
 const e=new VoiceEditor();e.add('title','План');const before=structuredClone(e.document);
 for(const command of ['Оформи слайд','Сделай заголовок крупнее и красным','Ширина сто и удали заголовок','Выровняй заголовок по центру и удали карточку']){
  expect(localEdits(e,command)).toBe(false);expect(e.document).toEqual(before);
 }
 expect(e.undoStack).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});
