export type VoicePhrase = {utteranceId:string;contextKey:string;receivedAt:number;recognitionLagMs:number};
type Interval = {start:number;end:number;key:string};

/** Audio offsets, not ASR delivery time, identify the context of a spoken command. */
export class VoiceContextTimeline {
  private intervals:Interval[]=[];
  private lastCapture=0;
  clear(){this.intervals=[];}
  record(start:number,end:number,key:string,now=performance.now()){
    const last=this.intervals.at(-1);
    if(last&&last.key===key&&last.end===start)last.end=end;
    else this.intervals.push({start,end,key});
    this.lastCapture=now;
    const cutoff=end-120000;
    while(this.intervals.length>1&&(this.intervals[0].end<cutoff||this.intervals.length>512))this.intervals.shift();
  }
  resolve(start:unknown,end:unknown,currentKey:string,now=performance.now()):{key:string;lagMs:number}|undefined{
    if(typeof start!=='number'||typeof end!=='number'||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start)return;
    const first=this.intervals.find(i=>i.start<=start&&i.end>start),last=this.intervals.at(-1);
    if(!first||!last||end>last.end+1||first.key!==currentKey)return;
    const covered=this.intervals.filter(i=>i.end>start&&i.start<end);
    if(!covered.length||covered.at(-1)!.end<end||covered.some((i,n)=>i.key!==currentKey||(n>0&&i.start!==covered[n-1].end)))return;
    const lagMs=Math.max(0,now-this.lastCapture+last.end-end);
    if(lagMs>10000)return;
    return {key:currentKey,lagMs};
  }
}

export type DeleteConfirmation={deckId:string;variant:string;revision:string;slideId:string;index:number;expiresAt:number};
export function deletionStillValid(pending:DeleteConfirmation,current:{deckId:string;variant:string;revision:string;slideIds:string[]},now=performance.now()){
  return now<pending.expiresAt&&pending.deckId===current.deckId&&pending.variant===current.variant
    &&pending.revision===current.revision&&current.slideIds[pending.index-1]===pending.slideId;
}
