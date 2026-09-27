const units='ноль один два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать'.split(' ');
const tens='двадцать тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто'.split(' ');
export const normalizeVoice=(s:string)=>s.toLowerCase().replace(/ё/g,'е').replace(/\s+/g,' ').trim();
export function voiceNumber(raw:string):number|undefined{
 const s=normalizeVoice(raw).replace(/^(одну|одна)$/,'один').replace(/^две$/,'два');
 if(/^\d+$/.test(s))return Number(s);
 if(units.includes(s))return units.indexOf(s);
 const parts=s.split(' '),t=tens.indexOf(parts[0]),u=units.indexOf(parts[1]);
 if(t>=0&&(parts.length===1||parts.length===2&&u>0&&u<10))return (t+2)*10+(parts.length===2?u:0);
 if(s==='сто')return 100;
 const ordinal=s.match(/^(перв|втор|трет|четверт|пят|шест|седьм|восьм|девят|десят)(?:ый|ой|ий|ую|юю|ая|яя|ое|ее)$/);
 if(ordinal)return ['перв','втор','трет','четверт','пят','шест','седьм','восьм','девят','десят'].indexOf(ordinal[1])+1;
}
