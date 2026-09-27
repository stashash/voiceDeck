import {BASE_URL} from '../designer/api';

export class EditorServiceError extends Error{
 constructor(message:string,public code?:string){super(message);this.name='EditorServiceError';}
}

/** Settles even a stalled transport that ignores AbortSignal. */
export async function editorRequest<T>(path:string, body?:unknown, options:{method?:string;signal?:AbortSignal;timeout?:number}={}):Promise<T>{
 const controller=new AbortController();
 let rejectAbort:(reason:Error)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject;});
 const stop=()=>{controller.abort();rejectAbort(new Error('Запрос отменён'));};
 options.signal?.addEventListener('abort',stop,{once:true});
 const timer=setTimeout(()=>{controller.abort();rejectAbort(new Error('Истекло время ожидания. Документ не изменён.'));},options.timeout??10000);
 try{
  if(options.signal?.aborted)throw new Error('Запрос отменён');
  const work=(async()=>{
   const response=await fetch(BASE_URL+'/editor/'+path,{method:options.method??(body===undefined?'GET':'POST'),headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
   const data=await response.json();
   if(!response.ok)throw new EditorServiceError(typeof data.detail==='string'?data.detail:data.detail?.message??'Сервис отклонил запрос',data.detail?.code);
   return data as T;
  })();
  return await Promise.race([work,aborted]);
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',stop);}
}
