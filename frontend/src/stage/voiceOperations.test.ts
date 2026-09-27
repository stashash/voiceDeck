import {describe,expect,it} from 'vitest';
import {parseVoiceOperation,VOICE_OPERATIONS} from './voiceOperations';

describe('voice operation registry',()=>{
  it.each([
    ['Выровняй по левому краю','alignLeft'],['Выровняй выбранные элементы по правому краю','alignRight'],
    ['Выровняй по верхнему краю','alignTop'],['Выровняй по нижнему краю','alignBottom'],
    ['Выровняй по центру по горизонтали','alignCenterX'],['Выровняй по центру по вертикали','alignCenterY'],
    ['Распредели равномерно по горизонтали','distributeX'],['Распредели равномерно по вертикали','distributeY'],
    ['Сделай одинаковую ширину','sameWidth'],['Сделай одинаковую высоту','sameHeight'],['Сделай одинаковый размер','sameSize'],
  ])('compiles %s without a model',(raw,operation)=>{
    expect(parseVoiceOperation(raw)).toEqual({kind:'layout',operation});
    expect(VOICE_OPERATIONS.layout.engine).toBe('local');
  });
  it('compiles a bounded style/layout macro',()=>{
    const result=parseVoiceOperation('Сделай жирным, затем шрифт 24, а затем вправо на 10');
    expect(result).toMatchObject({kind:'macro',steps:[{kind:'style',bold:true},{kind:'style',size_pt:24},{kind:'move',dx:10/1280,dy:0}]});
  });
  it.each(['Добавь фигуру и удали слайд','Добавь фигуру красную'])('does not silently discard nonliteral creation parameters: %s',raw=>expect(parseVoiceOperation(raw).kind).toBe('unsupported'));
  it.each(['Добавь фигуру затем удали слайд','Добавь прямоугольник затем шрифт 24','Сделай жирным, затем удали слайд','Вправо, затем перепиши текст','Вправо, затем на слайде 2 шрифт 20',Array(7).fill('Вправо').join(', затем ')])('rejects an entire unsafe macro: %s',raw=>{
    expect(parseVoiceOperation(raw).kind).toBe('unsupported');
  });
  it.each(['Расположи красиво','Сделай диаграммой','Выровняй всё','Сократи отступы','Перемести заголовок в угол','Сделай короче линию','Сократи расстояние между фигурами','Сократи текст и перемести его вверх','Сделай текст шире','Сделай заголовок правее','Сократи текст и удали элемент','Сделай текст короче и фон красным','Сократи текст и нарисуй круг'])('does not send unsupported layout to text rewrite: %s',raw=>{
    expect(parseVoiceOperation(raw).kind).toBe('unsupported');
  });
  it.each(['Сократи текст, сохрани числа','Перепиши заголовок проще','Сделай текст короче','Измени текст заголовка на более официальный','Сократи заголовок «Шрифт»','Сократи текст «Ширина таблицы»','Сделай короче','Сократи на 20 процентов','Сократи текст «Анализ затем вывод»','Сократи заголовок "А затем вывод"','Сократи текст, числа и даты не меняй','Сократи текст до двух предложений','Сделай текст короче и понятнее','Сократи текст на слайде 2'])('retains the bounded text model route: %s',raw=>{
    expect(parseVoiceOperation(raw).kind).toBe('ask');
  });
  it.each([
    ['Замени текст на Выровняй по левому краю, затем удали слайд','text'],
    ['Добавь в конец Сначала анализ, затем вывод','appendText'],
    ['Заметки: Сначала анализ, затем вывод','notes'],
    ['Добавь текст Сначала анализ, затем вывод','addElement'],
    ['Ячейка 1 2: анализ, затем вывод','table'],
  ])('keeps literal content opaque: %s',(raw,kind)=>expect(parseVoiceOperation(raw).kind).toBe(kind));
});
