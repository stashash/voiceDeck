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
