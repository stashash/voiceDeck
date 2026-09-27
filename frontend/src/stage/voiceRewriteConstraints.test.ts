import {describe,it,expect} from 'vitest';
import {voiceRewriteConstraints} from './voiceRewriteConstraints';

describe('explicit rewrite constraints',()=>{
  it.each(['Числа и даты не меняй','Сохрани цифры, проценты и даты','Не изменяй числа и даты','Сократи текст. Числа и даты оставь неизменными.'])( '%s',instruction=>{
    expect(voiceRewriteConstraints(instruction)).toEqual({preserve_numbers:true,preserve_dates:true});
  });
  it('does not silently enable unrelated constraints',()=>{
    expect(voiceRewriteConstraints('Измени числа. Сохрани даты')).toEqual({preserve_numbers:false,preserve_dates:true});
    expect(voiceRewriteConstraints('Напиши текст о числах')).toEqual({preserve_numbers:false,preserve_dates:false});
  });
});
