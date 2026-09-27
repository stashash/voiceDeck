/** Explicit user constraints are checked again against model output on the server. */
export function voiceRewriteConstraints(instruction:string){
  const protectedClauses=instruction.toLowerCase().split(/[.!?;]/u).filter(clause=>
    /не\s+(?:меняй|изменяй|трогай)|сохран(?:и|яй)|оставь[^,]{0,40}неизмен/u.test(clause));
  return {
    preserve_numbers:protectedClauses.some(clause=>/(?:цифр|числ|процент)[а-яё]*/u.test(clause)),
    preserve_dates:protectedClauses.some(clause=>/дат[а-яё]*/u.test(clause)),
  };
}
