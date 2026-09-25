export type Sentence={id:string;text:string;t0:number;t1:number};
export type Chunk={id:string;rev:number;status:'provisional'|'confirmed';sentence_ids:string[];text:string;t0:number;t1:number;updated_at:number;source?:'human'|'drift'|'curator'|'confirmer'|'offline'};
export type Slide={chunk_id:string;rev:number;title:string|null;bullets:string[];notes:string;source:string;pattern_id?:string;html?:string};
export type State={seq:number;sentences:Record<string,Sentence>;chunks:Record<string,Chunk>;slides:Record<string,Slide>;partial:string};
export const initial=():State=>({seq:0,sentences:{},chunks:{},slides:{},partial:''});
export type Event={type:string;seq?:number;sentence?:Sentence;chunk?:Chunk;slide?:Slide;replace_ids?:string[];chunks?:Chunk[];text?:string;[key:string]:unknown};
export function reduce(state:State,e:Event):State{
  if(e.type==='partial')return {...state,partial:e.text??''};
  if(!e.seq||e.seq<=state.seq)return state;
  if(e.seq!==state.seq+1)throw new Error('Пропуск событий: требуется восстановление');
  let s={...state,seq:e.seq};
  if(e.type==='final'&&e.sentence)s={...s,sentences:{...s.sentences,[e.sentence.id]:e.sentence},partial:''};
  if(e.type==='chunk'&&e.chunk)s={...s,chunks:{...s.chunks,[e.chunk.id]:e.chunk}};
  if(e.type==='chunk_revise'){
    const chunks={...s.chunks},slides={...s.slides};
    // Reject stale replacement atomically, including its associated deletions.
    if((e.chunks??[]).some(c=>chunks[c.id]&&chunks[c.id].rev>=c.rev))return s;
    const before={...s.chunks};
    for(const id of e.replace_ids??[]){delete chunks[id];delete slides[id];}
    for(const c of e.chunks??[]){
      chunks[c.id]=c;
      // Подтверждение не меняет состав фрагмента: слайд остаётся, сервис не собирает его заново.
      const old=before[c.id],slide=s.slides[c.id];
      if(old&&slide&&old.sentence_ids.join()===c.sentence_ids.join())slides[c.id]={...slide,rev:c.rev};
    }
    s={...s,chunks,slides};
  }
  if(e.type==='slide'&&e.slide&&s.chunks[e.slide.chunk_id]?.rev===e.slide.rev)s={...s,slides:{...s.slides,[e.slide.chunk_id]:e.slide}};
  return s;
}
