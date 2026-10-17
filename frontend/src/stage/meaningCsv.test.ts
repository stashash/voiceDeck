import {describe,expect,it} from 'vitest';
import {calculateCsvChange,parseMeaningCsv,readMeaningCsv,type CsvSelection,type MeaningCsv} from './meaningCsv';

const selection:CsvSelection={metric:1,label:0,base:0,comparison:1,decimal:'.',comparable:true};
function csv(text='period,revenue\nJan,100\nFeb,125'):MeaningCsv{
 const [head,...rows]=parseMeaningCsv(text);return {filename:'revenue.csv',sha256:'a'.repeat(64),headers:head.cells,rows};
}
describe('bounded RFC4180 CSV import',()=>{
 it('preserves escaped quotes, commas and CRLF in quoted cells with physical line provenance',()=>{
  const rows=parseMeaningCsv('\ufeffperiod,revenue,note\r\n"Jan, 2026",100,"first\r\nsecond ""quoted"""\r\nFeb,125,ok\r\n');
  expect(rows[1]).toEqual({cells:['Jan, 2026','100','first\r\nsecond "quoted"'],record:2,lineStart:2,lineEnd:3});
  expect(rows[2].lineStart).toBe(4);
 });
 it('reads semicolon files only by explicit selection and leaves formulas as unevaluated strings',()=>{
  expect(parseMeaningCsv('period;value\nJan;"1,5"\nFeb;=1+2',';')[2].cells[1]).toBe('=1+2');
  expect(()=>parseMeaningCsv('period;value\nJan;1\nFeb;2')).toThrow('заголовка');
 });
 it('rejects malformed quotes, ragged rows, invalid headers and oversized input',()=>{
  for(const text of ['period,value\nJan,"100\nFeb,125','period,value\nJan,"100"x\nFeb,125','period,value\nJ"an,100\nFeb,125','period,value\nJan,100,x\nFeb,125',',value\nJan,100\nFeb,125','value,value\nJan,100\nFeb,125','period,value\nJan,100','period,value\nJan,\0\nFeb,125'])expect(()=>parseMeaningCsv(text)).toThrow();
  expect(()=>parseMeaningCsv('x'.repeat(1024*1024+1))).toThrow('1 МиБ');
  expect(()=>parseMeaningCsv('period,value\nJan,'+'1'.repeat(2001)+'\nFeb,2')).toThrow('2000 символов');
  expect(()=>parseMeaningCsv('period,value\n'+Array.from({length:2001},(_,i)=>`p${i},1`).join('\n'))).toThrow('2000 строк');
 });
 it('requires UTF-8 and hashes original bytes so different files have different provenance',async()=>{
  const a=await readMeaningCsv(new File(['period,value\r\nJan,100\r\nFeb,125'],'data.csv'));
  const b=await readMeaningCsv(new File(['period,value\nJan,100\nFeb,125'],'data.csv'));
  expect(a.sha256).toMatch(/^[0-9a-f]{64}$/);expect(a.sha256).not.toBe(b.sha256);
  await expect(readMeaningCsv(new File([new Uint8Array([0xff])],'legacy.csv'))).rejects.toThrow('UTF-8');
 });
});
describe('reproducible metric comparison',()=>{
 it('computes percent using exact decimals and includes formula, raw inputs and file/row references',()=>{
  const result=calculateCsvChange(csv(),selection);
  expect(result.percent).toBe('25');expect(result.formula).toBe('(125 − 100) / 100 × 100 = 25%');
  expect(result.base).toMatchObject({record:2,lines:[2,2],raw:'100',value:'100'});
  expect(result.comparison.lines).toEqual([3,3]);expect(result.source_id.length).toBeLessThanOrEqual(100);
  expect(JSON.parse(result.source)).toMatchObject({file:'revenue.csv',column:2,label_column:1,sha256:'a'.repeat(64),algorithm:'percent-change-decimal-v1'});
 });
 it('handles decrease, zero comparison, large and small decimals, comma decimals and explicit rounding',()=>{
  const percent=(a:string,b:string)=>calculateCsvChange(csv(`period,value\nA,${a}\nB,${b}`),selection).percent;
  expect(percent('125','100')).toBe('-20');expect(percent('100','0')).toBe('-100');
  expect(percent('0.1','0.3')).toBe('200');expect(percent('3','4')).toBe('33.333333');
  expect(percent('6','7')).toBe('16.666667');expect(percent('9007199254740993','9007199254740994')).toBe('0');
  expect(percent('0.000000000001','0.000000000002')).toBe('100');
  const data=csv('period,value\nA,"1,5"\nB,"1,8"');expect(calculateCsvChange(data,{...selection,decimal:','}).percent).toBe('20');
 });
 it('blocks zero or negative base, missing/invalid or incompatible values and formulas',()=>{
  for(const base of ['0','-1','','N/A','NaN','Infinity','1e3','1 000','1,000','100%','$100','=SUM(A1)','0.0000000000001']){
   const value=base.includes(',')?`"${base}"`:base;
   expect(()=>calculateCsvChange(csv(`period,value\nA,${value}\nB,125`),selection)).toThrow();
  }
  expect(()=>calculateCsvChange(csv('period,value\nA,100\nB,-1'),selection)).toThrow('Отрицательное');
  expect(()=>calculateCsvChange(csv(),{...selection,comparable:false})).toThrow('сопоставимость');
  expect(()=>calculateCsvChange(csv(),{...selection,base:1})).toThrow('разные строки');
  expect(()=>calculateCsvChange(csv(),{...selection,metric:0})).toThrow('отдельные');
  expect(()=>calculateCsvChange(csv('period,value\nA,100\nA,125'),selection)).toThrow('разные непустые');
 });
});
