/** Bounded RFC4180 reader. CSV cells are data; formulas are never evaluated. */
export const CSV_MAX_BYTES=1024*1024;
export type CsvRow={cells:string[];record:number;lineStart:number;lineEnd:number};
export type MeaningCsv={filename:string;sha256:string;headers:string[];rows:CsvRow[]};
export type CsvSelection={metric:number;label:number;base:number;comparison:number;decimal:'.'|',';comparable:boolean};
export type CsvCalculation={source_id:string;source:string;filename:string;sha256:string;metric:string;column:number;base:{record:number;lines:[number,number];label:string;raw:string;value:string};comparison:{record:number;lines:[number,number];label:string;raw:string;value:string};formula:string;percent:string;rounding:string};

export function parseMeaningCsv(text:string,delimiter:','|';'=','):CsvRow[]{
 if(text.length>CSV_MAX_BYTES)throw Error('CSV превышает 1 МиБ');
 if(text.includes('\0'))throw Error('CSV содержит нулевой байт');
 if(delimiter!==','&&delimiter!==';')throw Error('Выберите разделитель: запятая или точка с запятой');
 if(text.charCodeAt(0)===0xfeff)text=text.slice(1);
 const rows:CsvRow[]=[];let cells:string[]=[],cell='',quoted=false,closed=false,line=1,start=1;
 const field=()=>{if(cell.length>2000)throw Error('Ячейка CSV превышает 2000 символов');cells.push(cell);cell='';closed=false;if(cells.length>50)throw Error('CSV содержит больше 50 столбцов');};
 const record=()=>{field();rows.push({cells,record:rows.length+1,lineStart:start,lineEnd:line});cells=[];if(rows.length>2001)throw Error('CSV содержит больше 2000 строк данных');};
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){
   if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}
   else if(c==='\r'||c==='\n'){if(c==='\r'&&text[i+1]==='\n'){cell+='\r\n';i++;}else cell+=c;line++;}
   else cell+=c;
  }else if(c==='"'){if(cell||closed)throw Error(`Некорректная кавычка в строке ${line}`);quoted=true;}
  else if(c===delimiter)field();
  else if(c==='\r'||c==='\n'){record();if(c==='\r'&&text[i+1]==='\n')i++;line++;start=line;}
  else{if(closed)throw Error(`Лишние символы после кавычки в строке ${line}`);cell+=c;}
  if(cell.length>2000)throw Error('Ячейка CSV превышает 2000 символов');
 }
 if(quoted)throw Error('Незакрытая кавычка в CSV');
 if(cell||cells.length||closed)record();
 if(rows.length<3)throw Error('Нужны заголовок и минимум две строки данных');
 const headers=rows[0].cells;
 if(headers.length<2||headers.some(x=>!x.trim())||new Set(headers.map(x=>x.trim())).size!==headers.length)throw Error('Нужны минимум два непустых уникальных заголовка');
 if(rows.some(row=>row.cells.length!==headers.length))throw Error('Количество столбцов в строках CSV различается');
 return rows;
}

export async function readMeaningCsv(file:File,delimiter:','|';'=','):Promise<MeaningCsv>{
 if(file.size>CSV_MAX_BYTES)throw Error('CSV превышает 1 МиБ');
 const bytes=await file.arrayBuffer();
 let text:string;
 try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('Сохраните CSV в кодировке UTF-8');}
 const records=parseMeaningCsv(text,delimiter);
 const hash=await crypto.subtle.digest('SHA-256',bytes);
 return {filename:file.name.slice(0,300),sha256:Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join(''),headers:records[0].cells,rows:records.slice(1)};
}

function decimalValue(raw:string,decimal:'.'|','){
 const value=raw.trim();
 const expression=decimal==='.'?/^[+-]?\d+(?:\.\d{1,12})?$/:/^[+-]?\d+(?:,\d{1,12})?$/;
 if(!expression.test(value)||value.replace(/[^0-9]/g,'').length>24)throw Error('Нужны обычные числа без валюты, %, разделителей тысяч и формул (не более 12 знаков после запятой)');
 const normalized=value.replace(',','.');
 const [whole,fraction='']=normalized.replace(/^[+-]/,'').split('.');
 const scale=10n**BigInt(fraction.length);
 return {raw,value:normalized,units:BigInt(whole+fraction)*(normalized.startsWith('-')?-1n:1n),scale};
}

/** Integer arithmetic, rounded to six decimal places; no LLM arithmetic. */
export function calculateCsvChange(csv:MeaningCsv,selection:CsvSelection):CsvCalculation{
 const {metric,label,base,comparison,decimal,comparable}=selection;
 if(!comparable)throw Error('Подтвердите одинаковые единицы измерения и сопоставимость периодов');
 if(![metric,label,base,comparison].every(Number.isInteger)||metric<0||label<0||metric>=csv.headers.length||label>=csv.headers.length||metric===label)throw Error('Выберите отдельные столбцы метрики и периода');
 if(base===comparison||!csv.rows[base]||!csv.rows[comparison])throw Error('Выберите две разные строки данных');
 if(decimal!=='.'&&decimal!==',')throw Error('Выберите десятичный разделитель');
 const a=csv.rows[base],b=csv.rows[comparison],av=decimalValue(a.cells[metric],decimal),bv=decimalValue(b.cells[metric],decimal);
 if(av.units<=0n)throw Error('Базовое значение должно быть больше нуля');
 if(bv.units<0n)throw Error('Отрицательное сравниваемое значение не поддерживается в этом расчёте');
 if(!a.cells[label].trim()||!b.cells[label].trim()||a.cells[label].trim()===b.cells[label].trim())throw Error('Укажите разные непустые периоды/названия строк');
 const denominator=av.units*bv.scale;
 const numerator=(bv.units*av.scale-denominator)*100n*1000000n;
 const negative=numerator<0n,absolute=negative?-numerator:numerator;
 const rounded=(absolute+denominator/2n)/denominator;
 const digits=rounded.toString().padStart(7,'0');
 const percent=(negative&&rounded!==0n?'-':'')+digits.slice(0,-6)+(digits.endsWith('000000')?'':'.'+digits.slice(-6).replace(/0+$/,''));
 const formula=`(${bv.value} − ${av.value}) / ${av.value} × 100 = ${percent}%`;
 const result:CsvCalculation={source_id:`csv:${csv.sha256}:c${metric+1}:r${a.record}-${b.record}`,source:'',filename:csv.filename,sha256:csv.sha256,metric:csv.headers[metric],column:metric+1,
  base:{record:a.record,lines:[a.lineStart,a.lineEnd],label:a.cells[label],raw:av.raw,value:av.value},
  comparison:{record:b.record,lines:[b.lineStart,b.lineEnd],label:b.cells[label],raw:bv.raw,value:bv.value},formula,percent,rounding:'Точная десятичная арифметика; результат округлён до 6 знаков после точки. Сопоставимость подтверждена автором.'};
 result.source=JSON.stringify({file:csv.filename,sha256:csv.sha256,column:result.column,metric:result.metric,label_column:label+1,decimal_separator:decimal,algorithm:'percent-change-decimal-v1',base:result.base,comparison:result.comparison,formula,rounding:result.rounding},null,2);
 return result;
}
