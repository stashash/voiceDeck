import {describe,it,expect,vi,afterEach} from 'vitest';
import {
 BASE_URL,absoluteUrl,assetUrl,fileUrl,fixFindings,watchDeckEvents,
 uploadDesignSystem,patchDesignSystem,listDesignSystemItems,listDecks,
 listAgents,checkAgent,getAgentAssignments,setAgentAssignments,
 patchSlideText,slidesAction,
} from './api';

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

describe('дизайн-системы',()=>{
 it('загрузка не-pptx отдаёт текст ошибки сервиса дословно',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:400,json:async()=>({detail:'Файл не pptx'})}));
  const file=new File(['x'],'Итоги_Q3.pdf');
  await expect(uploadDesignSystem(file)).rejects.toThrow('Файл не pptx');
 });
 it('list отдаёт items из ответа сервиса',async()=>{
  const items=[{id:'ds1',name:'VK Tech',source_file:'a.pptx',patterns:5,preview:null,created_at:'',describe_status:'done' as const}];
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({ids:['ds1'],items})}));
  await expect(listDesignSystemItems()).resolves.toEqual(items);
 });
 it('patch шлёт PATCH с телом решения автора',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({id:'ds1'})});
  vi.stubGlobal('fetch',fetchMock);
  await patchDesignSystem('ds1',{pattern_overrides:{p1:false},removal_confirmed:true});
  const [reqUrl,init]=fetchMock.mock.calls[0];
  expect(reqUrl).toBe(`${BASE_URL}/design-systems/ds1`);
  expect(init.method).toBe('PATCH');
  expect(JSON.parse(init.body)).toEqual({pattern_overrides:{p1:false},removal_confirmed:true});
 });
});

describe('презентации: список и правка',()=>{
 it('listDecks отдаёт items',async()=>{
  const items=[{id:'d1',title:'Т',design_system_id:'ds1',slides:5,status:'done',started_at:'',preview:null}];
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items})}));
  await expect(listDecks()).resolves.toEqual(items);
 });
 it('patchSlideText шлёт element_id и text на адрес слайда',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({status:'done'})});
  vi.stubGlobal('fetch',fetchMock);
  await patchSlideText('d1','b',5,'el1','новый текст');
  const [reqUrl,init]=fetchMock.mock.calls[0];
  expect(reqUrl).toBe(`${BASE_URL}/decks/d1/b/slides/5/text`);
  expect(JSON.parse(init.body)).toEqual({element_id:'el1',text:'новый текст'});
 });
 it('slidesAction шлёт действие ленты слайдов',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({status:'done'})});
  vi.stubGlobal('fetch',fetchMock);
  await slidesAction('d1','a',{action:'copy',index:2});
  const [reqUrl,init]=fetchMock.mock.calls[0];
  expect(reqUrl).toBe(`${BASE_URL}/decks/d1/a/slides`);
  expect(JSON.parse(init.body)).toEqual({action:'copy',index:2});
 });
});

describe('агенты',()=>{
 it('listAgents отдаёт items',async()=>{
  const items=[{id:'cli:claude',kind:'cli' as const,name:'Claude Code',detail:'2.1.270',found:true,model:null}];
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items})}));
  await expect(listAgents()).resolves.toEqual(items);
 });
 it('checkAgent зовёт POST /agents/{id}/check',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({ok:true,images:true,seconds:1.2,message:'отвечает'})});
  vi.stubGlobal('fetch',fetchMock);
  await checkAgent('cli:claude');
  const [reqUrl,init]=fetchMock.mock.calls[0];
  expect(reqUrl).toBe(`${BASE_URL}/agents/cli%3Aclaude/check`);
  expect(init.method).toBe('POST');
 });
 it('назначения читаются и сохраняются PUT-ом',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({deck:'cli:claude',live:'local:qwen',describe:'local:qwen'})});
  vi.stubGlobal('fetch',fetchMock);
  await getAgentAssignments();
  expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/settings/agents`);
  await setAgentAssignments({deck:'cli:claude',live:'local:qwen',describe:'local:qwen'});
  expect(fetchMock.mock.calls[1][1].method).toBe('PUT');
 });
});
