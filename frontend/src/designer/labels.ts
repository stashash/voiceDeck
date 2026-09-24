// Русские названия типов образцов: один словарь на все экраны (docs/design/canvas/gen.py, KIND).
export const KIND_LABEL: Record<string, string> = {
  title: 'Титульный', steps: 'Шаги', image_text: 'Картинка и текст', cards: 'Карточки', other: 'Другое',
  table: 'Таблица', big_number: 'Большое число', chart: 'Диаграмма', bullets: 'Список', cta: 'Призыв',
  timeline: 'Хронология', section: 'Раздел', thanks: 'Финальный', team: 'Команда', code: 'Код',
  quote: 'Цитата', compare: 'Сравнение', agenda: 'Содержание',
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

// «1 слайд», «3 слайда», «13 слайдов»: русское число с существительным.
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10, mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? one
    : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
  return `${n} ${word}`;
}
