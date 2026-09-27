import {editorRequest} from './editorRequest';
export type ModelStatus={state:'ready'|'cold'|'loading'|'error';model:string;message?:string};

function pause(signal:AbortSignal){
 return new Promise<void>((resolve,reject)=>{
  const stop=()=>{clearTimeout(timer);signal.removeEventListener('abort',stop);reject(Error('Запрос отменён'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',stop);resolve();},700);
  signal.addEventListener('abort',stop,{once:true});if(signal.aborted)stop();
 });
}

/** Only cold-start loading gets a separate budget; each editing request stays bounded. */
export async function prepareEditorModel(signal:AbortSignal,changed:(status:ModelStatus)=>void){
 const deadline=Date.now()+65000;
 let status=await editorRequest<ModelStatus>('intent/prepare',{}, {signal,timeout:4000});changed(status);
 while(status.state==='loading'||status.state==='cold'){
  if(Date.now()>=deadline)throw Error('Модель не загрузилась за минуту. Локальные команды доступны.');
  await pause(signal);
  status=await editorRequest<ModelStatus>('intent/model',undefined,{signal,timeout:4000});changed(status);
 }
 if(status.state==='error')throw Error(status.message??'Модель недоступна');
}
