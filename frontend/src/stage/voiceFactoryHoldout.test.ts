import {describe, expect, it} from 'vitest';
import {parseDeckVoice} from './deckVoice';

describe('factory holdout: generated-deck literal text and strict targets', () => {
  it.each([
    ['Замени текст на Удали слайд. Отмени! СТОП?', 'Удали слайд. Отмени! СТОП?'],
    ['Напиши API v2: Рост 20%, Ёж и ёлка.', 'API v2: Рост 20%, Ёж и ёлка.'],
    ['Измени текст: Следующий слайд; Выбери два.', 'Следующий слайд; Выбери два.'],
    ['Замени текст на «Не удалять: СЛАЙД 2!»', 'Не удалять: СЛАЙД 2!'],
  ])('preserves literal payload: %s', (phrase, text) => {
    expect(parseDeckVoice(phrase)).toEqual({kind: 'text', text});
  });

  it.each([
    ['Добавь в конец API v2. Готово!', {kind: 'appendText', text: 'API v2. Готово!'}],
    ['На слайде два напиши ВАЖНО: Рост 20%.', {kind: 'text', text: 'ВАЖНО: Рост 20%.', slide: 2}],
    ['Добавь текст API v2: Рост 20%.', {kind: 'addElement', elementType: 'text', text: 'API v2: Рост 20%.'}],
    ['Выбери элемент 999', {kind: 'element', number: 999}],
    ['На слайде 999 выбери элемент два', {kind: 'element', number: 2, slide: 999}],
    ['На слайде 0 напиши Не менять.', {kind: 'text', text: 'Не менять.', slide: 0}],
    ['Выбери элемент 0', {kind: 'element', number: 0}],
    ['Слайд 0', {kind: 'select', number: 0}],
    ['Вправо на двадцать три пикселя', {kind: 'move', dx: 23 / 1280, dy: 0}],
    ['Вверх на 37 пикселей', {kind: 'move', dx: 0, dy: -37 / 720}],
    ['Следующий слайд!', {kind: 'next'}],
    ['Предыдущий слайд.', {kind: 'previous'}],
    ['Отмени!', {kind: 'undo'}],
    ['Стоп.', {kind: 'cancel'}],
  ])('retains command meaning: %s', (phrase, expected) => {
    expect(parseDeckVoice(phrase as string)).toMatchObject(expected);
  });

  it.each(['Выбери элемент минус один', 'На неизвестном слайде напиши УПС', 'Выбери несуществующий объект'])
    ('does not send invalid explicit selection to a model: %s', phrase => {
      expect(parseDeckVoice(phrase).kind).toBe('unknown');
    });
});
