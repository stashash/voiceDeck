import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {CsvChangePreview,csvMeaningEvidence} from './MeaningCsvPanel';
import {MeaningPanel} from './MeaningPanel';
import {calculateCsvChange,parseMeaningCsv} from './meaningCsv';
import {VoiceEditor} from './voiceEditor';

function calculation(){const [head,...rows]=parseMeaningCsv('period,revenue\nJan,100\nFeb,125');return calculateCsvChange({filename:'<script>.csv',sha256:'a'.repeat(64),headers:head.cells,rows},{metric:1,label:0,base:0,comparison:1,decimal:'.',comparable:true});}
afterEach(()=>vi.unstubAllGlobals());
describe('CSV meaning UI and request integration',()=>{
 it('offers local file import and explicit separator in existing meaning panel',()=>{
  const editor=new VoiceEditor();editor.meaning.open=true;
  const html=renderToStaticMarkup(<MeaningPanel editor={editor} refresh={()=>{}}/>);
  expect(html).toContain('aria-label="Локальный CSV"');expect(html).toContain('type="file"');expect(html).toContain('Разделитель CSV');expect(html).toContain('Файл читается в браузере');
 });
 it('renders formula, precise source link and safe filename; expand action carries exact evidence',()=>{
  const c=calculation(),expand=vi.fn();const tree=CsvChangePreview({calculation:c,busy:false,onExpand:expand});
  const html=renderToStaticMarkup(tree);
  expect(html).toContain('(125 − 100) / 100 × 100 = 25%');expect(html).toContain(`href="#meaning-csv-${c.sha256}"`);expect(html).toContain('&lt;script&gt;.csv');expect(html).not.toContain('<script>');
  expect(html).toContain('строки 2–2 и 3–3');
  const button=(tree.props.children as React.ReactElement<{onClick?:()=>void}>[]).find(child=>child?.type==='button');
  button!.props.onClick!();expect(expand).toHaveBeenCalledWith(csvMeaningEvidence(c));
  expect(renderToStaticMarkup(<CsvChangePreview calculation={c} busy onExpand={expand}/>)).toContain('disabled=""');
 });
 it('accepts calculated evidence through local request and keeps full provenance after apply/undo',async()=>{
  const c=calculation(),editor=new VoiceEditor();editor.add('title','Результат');editor.save=vi.fn();const before=structuredClone(editor.document);
  const fetch=vi.fn(async(_url,init)=>{
   const p=JSON.parse(init.body as string);expect(p.context.calculation.formula).toBe(c.formula);expect(p.context.sources[c.source_id]).toBe(c.source);
   // Entire CSV is never sent: only the selected records and provenance.
   expect(p.context.calculation.base.record).toBe(2);expect(p.context.calculation.comparison.record).toBe(3);
   return {ok:true,json:async()=>({main_idea:'Рост',explanation:'Изменение 25%',details:[],evidence:[{source_id:c.source_id,quote:c.formula}],caveats:[],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version})} as Response;
  });vi.stubGlobal('fetch',fetch);
  await editor.meaning.request('Объясни вычисленный результат',()=>{},csvMeaningEvidence(c));expect(editor.meaning.error).toBe('');expect(editor.document).toEqual(before);
  await editor.meaning.retry(()=>{});expect(fetch).toHaveBeenCalledTimes(2);
  editor.meaning.apply('create_follow_up');expect(editor.current.notes).toContain(c.source);expect(editor.current.notes).toContain(c.sha256);editor.undo();expect(editor.document).toEqual(before);
 });
 it('invalidates CSV draft when selection/file changes and prevents retry from silently reusing old data',async()=>{
  const c=calculation(),editor=new VoiceEditor();
  vi.stubGlobal('fetch',vi.fn(async(_url,init)=>{const p=JSON.parse(init.body as string);return {ok:true,json:async()=>({main_idea:'Рост',explanation:'25%',details:[],evidence:[],caveats:[],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version})} as Response;}));
  await editor.meaning.request('Объясни',()=>{},csvMeaningEvidence(c));editor.meaning.invalidateEvidence();expect(editor.meaning.stale).toBe(true);expect(()=>editor.meaning.apply('update_current')).toThrow('изменился');await editor.meaning.retry(()=>{});expect(editor.meaning.error).toContain('Параметры CSV изменились');
 });
});
