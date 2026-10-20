/* Real UI recording, no mocked network responses. Requires Playwright + Chrome. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const OUT = path.resolve(process.env.DEMO_OUTPUT || path.join(ROOT, 'artifacts/stage2-demo/screencast'));
const BASE = process.env.DEMO_BASE_URL || 'http://localhost:8088';
const API = process.env.DEMO_API_URL || 'http://localhost:8090';
const SOURCE = path.join(ROOT, 'artifacts/stage2-demo/sources/90s-consulting-strategy-slides.pptx');
const CONTENT = path.join(ROOT, 'artifacts/stage2-demo/content-v2');
fs.mkdirSync(path.join(OUT, 'raw'), {recursive:true});
const state = {startedAt:new Date().toISOString(),base:BASE,api:API,stages:[],errors:[],downloads:[],syntheticData:true,networkMocks:false,stateReads:{count:0,maxConcurrent:0}};
let started;
let activeBrowser;
function mark(name, detail={}) { const stage={name,seconds:(Date.now()-started)/1000,...detail}; state.stages.push(stage); fs.writeFileSync(path.join(OUT,'capture-manifest.json'),JSON.stringify(state,null,2)); console.log(JSON.stringify(stage)); }
async function hold(page,seconds=3) { await page.waitForTimeout(seconds*1000); }
async function shot(page,name) { await page.screenshot({path:path.join(OUT,name+'.png')}); }

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 activeBrowser=browser;
 const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,recordVideo:{dir:path.join(OUT,'raw'),size:{width:1920,height:1080}},acceptDownloads:true});
 const page=await context.newPage(); started=Date.now();
 const pendingStateReads=new Set();
 page.on('request',request=>{if(request.method()==='GET' && /\/decks\/[a-z0-9]+$/.test(request.url())){pendingStateReads.add(request);state.stateReads.count++;state.stateReads.maxConcurrent=Math.max(state.stateReads.maxConcurrent,pendingStateReads.size)}});
 page.on('requestfinished',request=>pendingStateReads.delete(request));
 page.on('requestfailed',request=>pendingStateReads.delete(request));
 page.on('pageerror',error=>{state.errors.push(error.message); console.error('PAGEERROR',error.message)});
 try {
  await page.goto(BASE+'/#/'); await hold(page,4); mark('home');
  await page.getByRole('link',{name:'Дизайн-системы',exact:true}).click();
  await page.getByRole('link',{name:'Создать из pptx',exact:true}).click(); await hold(page,3); mark('template-upload-start');
  const templateResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/design-systems$/.test(r.url()),{timeout:180000});
  await page.locator('input[type=file][accept=".pptx"]').setInputFiles(SOURCE);
  const template=await (await templateResponse).json(); if(!template.id) throw Error('Template import failed: '+JSON.stringify(template));
  state.designSystemId=template.id; mark('template-upload-end',{designSystemId:template.id});
  await page.getByRole('heading',{name:'Брендбук и токены'}).waitFor({timeout:15000});
  await page.getByRole('heading',{name:'Брендбук и токены'}).scrollIntoViewIfNeeded(); await hold(page,4);
  mark('brandbook-upload-start');
  const brandResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/brandbook$/.test(r.url()),{timeout:30000});
  await page.locator('input[type=file][accept*=zip]').setInputFiles(path.join(ROOT,'frontend/public/brandbooks/local-brandbook.zip'));
  const brand=await (await brandResponse).json();
  if(!brand.applied_fields?.includes('logo') || !brand.applied_fields?.includes('chart_style')) throw Error('Brand rules were not applied');
  state.brandbook=brand; await hold(page,6); await shot(page,'brandbook'); mark('brandbook-applied');
  await page.getByRole('link',{name:'Создать презентацию',exact:true}).click();
  await page.locator('#brief').fill('Итоги учебного пилота. Все значения синтетические. Сохрани единицы и период источника. Отдели наблюдения от интерпретаций. Полный справочник вынеси в приложение.');
  await page.locator('.semantic-plan').scrollIntoViewIfNeeded(); await hold(page,4); mark('content-upload');
  const files=fs.readdirSync(CONTENT).filter(name=>/\.(csv|xlsx|json|md|txt)$/.test(name)).map(name=>path.join(CONTENT,name));
  if(files.length!==7) throw Error('Expected seven synthetic content files');
  await page.locator('.semantic-plan input[type=file]').setInputFiles(files); await hold(page,4);
  const analysisResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/insights\/plan$/.test(r.url()),{timeout:60000});
  await page.getByRole('button',{name:'Проанализировать',exact:true}).click();
  const bundle=await (await analysisResponse).json(); state.bundle=bundle;
  if(bundle.datasets?.length!==7) throw Error('Incomplete data bundle');
  mark('analysis-ready');
  for (const name of ['time_series.xlsx','category_shares.json','category_comparison.csv','missing_zero.csv','reference_201.csv']) {
   const tab=page.getByRole('tab',{name:new RegExp(name.replace(/\./g,'\\.'))});
   await tab.click(); await page.locator('.semantic-plan-detail').scrollIntoViewIfNeeded(); await hold(page,7);
   await shot(page,'analysis-'+name.replace(/\W/g,'_')); mark('analysis-dataset',{file:name});
  }
  const create=page.getByRole('button',{name:/Создать презентацию по выбранным таблицам/});
  await create.scrollIntoViewIfNeeded(); await hold(page,2);
  const createdResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/decks$/.test(r.url()),{timeout:60000});
  await create.click(); const created=await (await createdResponse).json(); if(!created.deck_id) throw Error('Deck creation failed');
  state.deckId=created.deck_id; await hold(page,6); mark('generation-wait-start',{deckId:created.deck_id});
  let deck; const deadline=Date.now()+1800000; let lastLog=0;
  for (;;) {
   const response=await context.request.get(API+'/decks/'+created.deck_id); deck=await response.json();
   const variants=['a','b','c'].map(code=>deck.variants?.[code]);
   if(variants.some(item=>item?.status==='error')) throw Error('Generation error: '+JSON.stringify(variants.map(item=>({status:item?.status,error:item?.error}))));
   if(variants.every(item=>item?.status==='done')) break;
   if(Date.now()>deadline) throw Error('Generation timed out');
   if(Date.now()-lastLog>30000) { console.log('WAIT',variants.map(item=>item?.status).join(',')); lastLog=Date.now(); }
   await hold(page,3);
  }
  state.finalDeck=deck; mark('generation-wait-end');
  await page.getByRole('link',{name:'Открыть и править',exact:true}).click();
  await page.locator('.edit-slide-stage').waitFor({timeout:60000}); await hold(page,6); mark('editor-ready');
  const plan=deck.variants.a.plan?.slides || deck.plan?.slides || [];
  const items=plan.map((intent,index)=>({intent,index}));
  const demonstrations=[
   ['trend',items.find(item=>item.intent.provenance?.file_name==='time_series.xlsx')],
   ['shares',items.find(item=>item.intent.provenance?.file_name==='category_shares.json')],
   ['comparison',items.find(item=>item.intent.provenance?.file_name==='category_comparison.csv')],
   ['missing',items.find(item=>item.intent.provenance?.file_name==='missing_zero.csv')],
   ['appendix',items.find(item=>item.intent.provenance?.file_name==='reference_201.csv' && item.intent.provenance?.page_index===1)],
  ];
  for(const [name,item] of demonstrations){
   if(!item) throw Error('Missing demonstration slide: '+name);
   await page.getByRole('link',{name:'Слайд '+(item.index+1),exact:true}).click();
   await hold(page,10); await shot(page,'result-'+name); mark('result-slide',{kind:name,index:item.index+1,title:item.intent.title});
  }
  await page.getByRole('button',{name:'Скачать: pptx, pdf или html',exact:true}).click(); await hold(page,4); mark('export-options');
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('.download-item').filter({hasText:'для рассылки'}).click()]);
  await download.saveAs(path.join(OUT,'demo.pdf')); state.downloads.push('demo.pdf'); await hold(page,4);
  for(const name of ['deck.pptx','deck.html','deck.pdf']){
   const response=await context.request.get(`${API}/decks/${created.deck_id}/a/files/${name}`);
   if(!response.ok()) throw Error('Export missing: '+name);
   fs.writeFileSync(path.join(OUT,name),await response.body());
  }
  fs.mkdirSync(path.join(OUT,'slides'),{recursive:true});
  for(let i=0;i<deck.variants.a.slide_images.length;i++){
   const url=deck.variants.a.slide_images[i]; const response=await context.request.get(url.startsWith('http')?url:API+url);
   if(!response.ok()) throw Error('Slide image missing '+(i+1));
   fs.writeFileSync(path.join(OUT,'slides',String(i+1).padStart(3,'0')+'.png'),await response.body());
  }
  await page.getByRole('link',{name:'Слайд 1',exact:true}).click(); await hold(page,4); mark('complete');
  if(state.stateReads.maxConcurrent>2) throw Error('Concurrent deck state request storm: '+state.stateReads.maxConcurrent);
  state.status='passed';
 } catch(error){ state.status='failed'; state.failure=error.stack; await shot(page,'failure').catch(()=>{}); throw error; }
 finally {
  state.finishedAt=new Date().toISOString(); state.browserErrors=state.errors;
  await context.close(); state.rawVideo=await page.video().path();
  fs.writeFileSync(path.join(OUT,'capture-manifest.json'),JSON.stringify(state,null,2));
  await browser.close();
 }
})().catch(async error=>{console.error(error.stack);if(activeBrowser)await activeBrowser.close().catch(()=>{});process.exitCode=1});
