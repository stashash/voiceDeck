import {describe,it,expect,vi,afterEach} from 'vitest';
import {BASE_URL,absoluteUrl,assetUrl,fileUrl,fixFindings,watchDeckEvents} from './api';

afterEach(()=>{vi.unstubAllGlobals();});

describe('адреса',()=>{
 it('assetUrl убирает префикс assets/ из пути пакета',()=>{
  expect(assetUrl('ds1','assets/a1.png')).toBe(`${BASE_URL}/design-systems/ds1/assets/a1.png`);
 });
 it('fileUrl строит адрес файла варианта',()=>{
  expect(fileUrl('deck1','b','deck.pptx')).toBe(`${BASE_URL}/decks/deck1/b/files/deck.pptx`);
 });
 it('absoluteUrl не трогает уже абсолютный адрес, а относительный достраивает базой',()=>{
  expect(absoluteUrl('https://cdn.example/a.png')).toBe('https://cdn.example/a.png');
  expect(absoluteUrl('/decks/1/a/slides/0.png')).toBe(`${BASE_URL}/decks/1/a/slides/0.png`);
 });
});

describe('поток событий колоды',()=>{
 class FakeEventSource{
  url:string;onmessage:((e:{data:string})=>void)|null=null;closed=false;
  constructor(url:string){this.url=url;}
  close(){this.closed=true;}
 }
 it('строит адрес потока и разбирает событие в обработчик',()=>{
  vi.stubGlobal('EventSource',FakeEventSource);
  const received:unknown[]=[];
  const source=watchDeckEvents('deck1',e=>received.push(e)) as unknown as FakeEventSource;
  expect(source.url).toBe(`${BASE_URL}/decks/deck1/events`);
  source.onmessage!({data:JSON.stringify({step:'plan',slide_index:null,variant:'a',at:1})});
  expect(received).toEqual([{step:'plan',slide_index:null,variant:'a',at:1}]);
 });
 it('пропускает битое событие без ошибки и не вызывает обработчик',()=>{
  vi.stubGlobal('EventSource',FakeEventSource);
  const received:unknown[]=[];
  const source=watchDeckEvents('deck1',e=>received.push(e)) as unknown as FakeEventSource;
  expect(()=>source.onmessage!({data:'{битый json'})).not.toThrow();
  expect(received).toHaveLength(0);
 });
});

describe('отправка починки',()=>{
 it('шлёт id находок и разбирает отчёт с новыми находками',async()=>{
  const report=[{finding_id:'f1',status:'fixed',what:'кегль уменьшен до предела блока'}];
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({report,findings:[]})});
  vi.stubGlobal('fetch',fetchMock);
  const res=await fixFindings('deck1','b',['f1','f2']);
  expect(res.report).toEqual(report);
  const [url,init]=fetchMock.mock.calls[0];
  expect(url).toBe(`${BASE_URL}/decks/deck1/b/fix`);
  expect(init.method).toBe('POST');
  expect(JSON.parse(init.body)).toEqual({finding_ids:['f1','f2']});
 });
 it('бросает понятную ошибку при неудачном ответе сервиса',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:500,json:async()=>({})}));
  await expect(fixFindings('deck1','a',['f1'])).rejects.toThrow('500');
 });
});
