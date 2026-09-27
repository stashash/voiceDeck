import type {Document} from './voiceEditor';
import {editorRequest} from './editorRequest';

type Attempt={request_id:string;base_revision:number;title:string;document:Document};
export type Draft={id:string;revision:number;title:string;document:Document;dirty?:boolean;attempt?:Attempt};
export type DraftStorage={get:(id:string)=>Promise<Draft|undefined>;put:(draft:Draft)=>Promise<void>};

async function database(){
 return new Promise<IDBDatabase>((resolve,reject)=>{
  const request=indexedDB.open('voicedeck-documents',1);
  request.onupgradeneeded=()=>request.result.createObjectStore('drafts',{keyPath:'id'});
  request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
 });
}
export const draftStorage:DraftStorage={
 async get(id){const db=await database();try{return await new Promise<Draft|undefined>((resolve,reject)=>{const r=db.transaction('drafts').objectStore('drafts').get(id);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}finally{db.close();}},
 async put(draft){const db=await database();try{await new Promise<void>((resolve,reject)=>{const tx=db.transaction('drafts','readwrite');tx.objectStore('drafts').put(draft);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}},
};

/** One in-flight save, durable retry identity, optimistic revision on the server. */
export class EditorPersistence{
 private timer?:ReturnType<typeof setTimeout>;
 private running?:Promise<void>;
 private generation=0;
 private persisted=-1;
 private stopped=false;
 status='Сохранено';
 error='';
 constructor(public draft:Draft,private changed:()=>void,private storage:DraftStorage=draftStorage){}
 schedule(document:Document,title:string){
  this.draft.document=document;this.draft.title=title;this.draft.dirty=true;this.generation++;
  this.status='Есть несохранённые правки';this.changed();clearTimeout(this.timer);
  this.timer=setTimeout(()=>void this.flush().catch(()=>{}),400);
 }
 async flush():Promise<void>{
  clearTimeout(this.timer);
  if(this.running)return this.running;
  if(this.stopped)throw new Error(this.error);
  this.running=this.write().finally(()=>{this.running=undefined;});
  return this.running;
 }
 private async write(){
  try{
   while(this.draft.dirty||this.draft.attempt){
    const generation=this.generation;
    const current=structuredClone(this.draft.document),title=this.draft.title;
    const attempt=this.draft.attempt??{request_id:crypto.randomUUID(),base_revision:this.draft.revision,title,document:current};
    this.draft.attempt=attempt;
    await this.storage.put(structuredClone(this.draft));
    this.status='Сохраняется';this.error='';this.changed();
    const response=await editorRequest<{revision:number}>('documents/'+this.draft.id,attempt,{method:'PUT'});
    this.draft.revision=response.revision;delete this.draft.attempt;
    // An uncertain previous request may be acknowledged after newer local edits.
    const same=JSON.stringify(attempt.document)===JSON.stringify(current)&&attempt.title===title;
    this.persisted=same?generation:-1;
    this.draft.dirty=this.generation!==this.persisted;
    await this.storage.put(structuredClone(this.draft));
   }
   this.status='Сохранено';
  }catch(error){this.error=String(error);this.status='Не синхронизировано';if(this.error.includes('другой вкладке'))this.stopped=true;await this.storage.put(structuredClone(this.draft)).catch(()=>{this.error+='; локальная резервная копия недоступна';});throw error;}
  finally{this.changed();}
 }
 retry(){this.stopped=false;return this.flush();}
 close(){clearTimeout(this.timer);void this.flush().catch(()=>{});}
}

export async function openDocument(id:string):Promise<Draft>{
 const local=await draftStorage.get(id).catch(()=>undefined);
 if(local?.dirty||local?.attempt)return local;
 try{return await editorRequest<Draft>('documents/'+id);}
 catch(error){if(local)return local;throw error;}
}
