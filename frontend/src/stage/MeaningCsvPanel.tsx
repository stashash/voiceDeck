import React,{useEffect,useRef,useState} from 'react';
import {calculateCsvChange,readMeaningCsv,type MeaningCsv,type CsvSelection,type CsvCalculation} from './meaningCsv';
import type {MeaningEvidenceContext} from './meaningExpansion';

export function csvMeaningEvidence(calculation:CsvCalculation):MeaningEvidenceContext{
 return {sources:{[calculation.source_id]:calculation.source},calculation};
}

export function CsvChangePreview({calculation,busy,onExpand}:{calculation:CsvCalculation;busy:boolean;onExpand:(context:MeaningEvidenceContext)=>void}){
 const c=calculation,anchor=`meaning-csv-${c.sha256}`;
 return <section aria-label="Воспроизводимый расчёт CSV">
  <p><strong>Изменение: {c.percent}%</strong></p><p aria-label="Формула изменения">{c.formula}</p>
  <p>Метрика: {c.metric}. База: {c.base.label} = {c.base.value}; сравнение: {c.comparison.label} = {c.comparison.value}.</p>
  <p>Источник: <a href={`#${anchor}`} onClick={event=>{event.preventDefault();document.getElementById(anchor)?.scrollIntoView({block:'nearest'});}}>{c.filename}, строки {c.base.lines.join('–')} и {c.comparison.lines.join('–')}, столбец {c.column}</a></p>
  <details id={anchor}><summary>Входные значения, строки и контрольная сумма</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.source}</pre></details>
  <p>{c.rounding} Расчёт не доказывает причины изменения и истинность исходного файла.</p>
  <button className="button" disabled={busy} onClick={()=>onExpand(csvMeaningEvidence(c))}>Раскрыть смысл вычисленного результата</button>
 </section>;
}

export function MeaningCsvPanel({busy,onExpand,onContextChange}:{busy:boolean;onExpand:(context:MeaningEvidenceContext)=>void;onContextChange:()=>void}){
 const [csv,setCsv]=useState<MeaningCsv>(),[file,setFile]=useState<File>(),[delimiter,setDelimiter]=useState<','|';'>(','),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [selection,setSelection]=useState<CsvSelection>({metric:1,label:0,base:0,comparison:1,decimal:'.',comparable:false});
 const sequence=useRef(0);useEffect(()=>()=>{sequence.current++;},[]);
 async function load(nextFile:File,nextDelimiter:','|';'){
  const version=++sequence.current;onContextChange();setCsv(undefined);setError('');setLoading(true);setFile(nextFile);setSelection(s=>({...s,metric:1,label:0,base:0,comparison:1,comparable:false}));
  try{const parsed=await readMeaningCsv(nextFile,nextDelimiter);if(version===sequence.current)setCsv(parsed);}
  catch(e){if(version===sequence.current)setError(String(e));}
  finally{if(version===sequence.current)setLoading(false);}
 }
 const change=(patch:Partial<CsvSelection>)=>{onContextChange();setSelection(s=>({...s,...patch,comparable:patch.comparable??false}));};
 let calculation:CsvCalculation|undefined,calculationError='';
 if(csv)try{calculation=calculateCsvChange(csv,selection);}catch(e){calculationError=String(e);}
 return <fieldset aria-label="Расчёт по локальному CSV">
  <legend>Раскрыть результат из CSV</legend>
  <p>Файл читается в браузере. Модель получит только выбранные значения, формулу и сведения об источнике. UTF-8, до 1 МиБ, 2000 строк, 50 столбцов. Формулы в ячейках не выполняются.</p>
  <label>Разделитель CSV<select aria-label="Разделитель CSV" value={delimiter} onChange={e=>{const next=e.target.value as ','|';';setDelimiter(next);if(file)void load(file,next);}}><option value=",">Запятая</option><option value=";">Точка с запятой</option></select></label>
  <label>Локальный CSV<input aria-label="Локальный CSV" type="file" accept=".csv,text/csv" onChange={e=>{const next=e.target.files?.[0];e.target.value='';if(next)void load(next,delimiter);}}/></label>
  {loading&&<p role="status">Читаю CSV…</p>}{error&&<p role="alert">{error}</p>}
  {csv&&<div>
   <p>{csv.filename} · {csv.rows.length} строк данных</p>
   <label>Столбец периода<select aria-label="Столбец периода" value={selection.label} onChange={e=>change({label:Number(e.target.value)})}>{csv.headers.map((header,i)=><option key={i} value={i}>{header}</option>)}</select></label>
   <label>Числовая метрика<select aria-label="Числовая метрика" value={selection.metric} onChange={e=>change({metric:Number(e.target.value)})}>{csv.headers.map((header,i)=><option key={i} value={i}>{header}</option>)}</select></label>
   <label>Десятичный разделитель<select aria-label="Десятичный разделитель" value={selection.decimal} onChange={e=>change({decimal:e.target.value as '.'|','})}><option value=".">Точка: 1234.56</option><option value=",">Запятая: 1234,56</option></select></label>
   {(['base','comparison'] as const).map(key=><label key={key}>{key==='base'?'Базовая строка':'Сравниваемая строка'}<select aria-label={key==='base'?'Базовая строка':'Сравниваемая строка'} value={selection[key]} onChange={e=>change({[key]:Number(e.target.value)})}>{csv.rows.map((row,i)=><option key={row.record} value={i}>{row.cells[selection.label]} · строка {row.lineStart} · {row.cells[selection.metric]}</option>)}</select></label>)}
   <label><input type="checkbox" checked={selection.comparable} onChange={e=>change({comparable:e.target.checked})}/>Подтверждаю одинаковые единицы измерения и сопоставимость периодов</label>
   {calculationError&&<p role="status">{calculationError}</p>}
   {calculation&&<CsvChangePreview calculation={calculation} busy={busy} onExpand={onExpand}/>}
  </div>}
 </fieldset>;
}
