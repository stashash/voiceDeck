import {Event} from './store';
export type Credentials={id:string;token:string;mode:string};
export class Transport {
  ws?:WebSocket;closed=false;timer?:ReturnType<typeof setTimeout>;attempt=0;ready=false;
  audioSeq=0;offset=0;packets=new Map<number,ArrayBuffer>();
  private acknowledgedAudio=0;
  private drains=new Set<{seq:number;finish:(error?:Error)=>void}>();
  constructor(public credentials:Credentials,private cursor:()=>number,private event:(e:Event)=>void,private status:(s:string)=>void,private failure:(s:string)=>void){this.connect();}
  connect(){
    if(this.closed)return;this.status('Подключение');this.ready=false;
    const ws=this.ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/session`);
    ws.onopen=()=>{if(!this.closed&&this.ws===ws)ws.send(JSON.stringify({type:'auth',session_id:this.credentials.id,token:this.credentials.token,from:this.cursor()}));};
    ws.onmessage=({data})=>{
      if(this.closed||this.ws!==ws)return;
      try{
        const e=JSON.parse(data);
        if(e.type==='ready'){
          if(e.seq!==this.cursor())throw new Error('История сессии рассинхронизирована');
          // Server restart loses only volatile audio. Rebase the bounded unacknowledged buffer.
          const restarted=e.audio_seq<this.acknowledgedAudio;
          const queued=[...this.packets.entries()].filter(([seq])=>restarted||seq>e.audio_seq).map(([,packet])=>packet);
          if(restarted){
            this.finishDrains(new Error('Сервер перезапущен во время передачи звука'));
            this.failure('Сервер перезапущен: незафиксированная аудиофраза могла быть потеряна. История текста восстановлена.');
          }
          this.packets.clear();this.audioSeq=e.audio_seq;this.offset=e.audio_offset;
          this.acknowledgedAudio=e.audio_seq;this.ready=true;this.attempt=0;
          this.status('Подключено');
          for(const packet of queued)this.audio(packet.slice(16));
          this.finishDrains();
        }else if(e.type==='audio_ack'){
          this.acknowledgedAudio=Math.max(this.acknowledgedAudio,Math.min(this.audioSeq,e.audio_seq));
          for(const seq of this.packets.keys())if(seq<=this.acknowledgedAudio)this.packets.delete(seq);
          this.finishDrains();
        }
        else if(e.type==='audio_resync'){ws.close();}
        else this.event(e);
      }catch(error){this.failure(String(error));ws.close();}
    };
    ws.onclose=({code})=>{
      if(this.ws!==ws)return;this.ready=false;if(this.closed)return;
      if([1000,1002,1003,1007,1008,1009,1010].includes(code)){
        this.closed=true;const error=new Error(`Соединение закрыто (${code})`);this.finishDrains(error);this.failure(error.message);return;
      }
      this.status('Восстановление связи');this.timer=setTimeout(()=>this.connect(),Math.min(10000,500*2**this.attempt++)+Math.random()*200);
    };
    ws.onerror=()=>{if(this.ws===ws)ws.close();};
  }
  send(data:object){if(!this.ready||this.ws?.readyState!==WebSocket.OPEN)throw new Error('Дождитесь восстановления соединения');this.ws.send(JSON.stringify(data));}
  audio(pcm:ArrayBuffer){
    if(this.closed)throw new Error('Соединение закрыто');
    if(this.packets.size>=938)throw new Error('Буфер звука заполнен (30 секунд). Запись остановлена; восстановите соединение.');
    const packet=new ArrayBuffer(16+pcm.byteLength),view=new DataView(packet);
    view.setBigUint64(0,BigInt(++this.audioSeq),true);view.setBigUint64(8,BigInt(this.offset),true);new Uint8Array(packet,16).set(new Uint8Array(pcm));this.offset+=pcm.byteLength/2;
    this.packets.set(this.audioSeq,packet);
    if(this.ready&&this.ws?.readyState===WebSocket.OPEN&&this.ws.bufferedAmount<1024*1024)this.ws.send(packet);
    else if(this.ready)this.ws?.close();
  }
  /** Wait for delivery of the audio queued at this call, including reconnect replay. */
  drain(timeoutMs=3000):Promise<void>{
    if(this.closed)return Promise.reject(new Error('Соединение закрыто'));
    if(!Number.isFinite(timeoutMs)||timeoutMs<0||timeoutMs>2147483647)return Promise.reject(new RangeError('Invalid audio drain timeout'));
    const seq=this.audioSeq;
    if(this.ready&&this.ws?.readyState===WebSocket.OPEN&&this.acknowledgedAudio>=seq)return Promise.resolve();
    return new Promise<void>((resolve,reject)=>{
      const waiter={seq,finish:(error?:Error)=>{clearTimeout(timer);this.drains.delete(waiter);if(error)reject(error);else resolve();}};
      const timer=setTimeout(()=>waiter.finish(new Error('Истекло время ожидания подтверждения звука')),timeoutMs);
      this.drains.add(waiter);
    });
  }
  private finishDrains(error?:Error){
    for(const waiter of this.drains)if(error||(this.ready&&this.ws?.readyState===WebSocket.OPEN&&this.acknowledgedAudio>=waiter.seq))waiter.finish(error);
  }
  close(){this.closed=true;this.ready=false;clearTimeout(this.timer);this.finishDrains(new Error('Соединение закрыто'));this.ws?.close();}
}
export type MicrophoneStopOptions={flush?:boolean;timeoutMs?:number};
export class Microphone {
  context?:AudioContext;stream?:MediaStream;node?:AudioWorkletNode;
  private generation=0;private flushId=0;private stopping?:Promise<void>;
  private pendingFlush?:{requestId:number;finish:(error?:Error)=>void};
  async start(frame:(pcm:ArrayBuffer)=>void,fail:(message:string)=>void){
    if(this.context||this.stream||this.pendingFlush)throw new Error('Микрофон уже запущен');
    const generation=++this.generation;this.stopping=undefined;
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
      if(this.generation!==generation){stream.getTracks().forEach(t=>t.stop());return;}
      this.stream=stream;
      const context=this.context=new AudioContext();await context.audioWorklet.addModule('/pcm-worklet.js');
      if(this.generation!==generation)return;
      const node=this.node=new AudioWorkletNode(context,'pcm16');
      node.port.onmessage=({data})=>{
        if(this.node!==node||this.generation!==generation)return;
        if(data?.type==='flush_ack'){
          if(data.requestId===this.pendingFlush?.requestId)this.pendingFlush?.finish();
        }else if(data instanceof ArrayBuffer){
          try{frame(data);}catch(error){
            this.pendingFlush?.finish(error instanceof Error?error:new Error(String(error)));
            void this.stop().catch(()=>{});fail(String(error));
          }
        }
      };
      const mute=this.context.createGain();mute.gain.value=0;
      this.context.createMediaStreamSource(this.stream).connect(this.node);this.node.connect(mute).connect(this.context.destination);
      this.stream.getAudioTracks()[0].onended=()=>fail('Микрофон отключён. Подключите устройство и возобновите запись.');
      this.context.onstatechange=()=>{if(this.context?.state==='suspended')fail('Аудиоконтекст приостановлен. Возобновите запись кнопкой.');};
      await this.context.resume();
    }catch(e){if(this.generation===generation)await this.stop();throw e;}
  }
  /** The editor opts in; plain stop discards the tail, including an in-flight flush. */
  stop({flush=false,timeoutMs=1000}:MicrophoneStopOptions={}):Promise<void>{
    if(this.stopping){
      if(!flush){
        ++this.generation;
        if(this.node)this.node.port.onmessage=null;
        this.pendingFlush?.finish(new Error('Передача остатка звука отменена'));
        return this.stopping.catch(()=>{});
      }
      return this.stopping;
    }
    if(!flush||!this.node)return this.stopping=this.release();
    const node=this.node,requestId=++this.flushId;
    const flushed=new Promise<void>((resolve,reject)=>{
      const timer=setTimeout(()=>this.pendingFlush?.finish(new Error('Истекло время ожидания остатка звука')),Number.isFinite(timeoutMs)&&timeoutMs>=0&&timeoutMs<=2147483647?timeoutMs:0);
      this.pendingFlush={requestId,finish:(error?:Error)=>{
        clearTimeout(timer);this.pendingFlush=undefined;if(error)reject(error);else resolve();
      }};
    });
    this.stopping=flushed.finally(()=>this.release());
    if(!Number.isFinite(timeoutMs)||timeoutMs<0||timeoutMs>2147483647)this.pendingFlush?.finish(new RangeError('Invalid microphone flush timeout'));
    else try{node.port.postMessage({type:'flush',requestId});}catch(error){this.pendingFlush?.finish(error instanceof Error?error:new Error(String(error)));}
    return this.stopping;
  }
  private async release(){
    ++this.generation;
    const {node,stream,context}=this;this.node=undefined;this.stream=undefined;this.context=undefined;
    let error:unknown;
    const cleanup=(action:()=>void)=>{try{action();}catch(e){error??=e;}};
    if(node){node.port.onmessage=null;cleanup(()=>node.disconnect());cleanup(()=>node.port.close());}
    stream?.getTracks().forEach(t=>{t.onended=null;cleanup(()=>t.stop());});
    if(context){
      context.onstatechange=null;
      let timer:ReturnType<typeof setTimeout>|undefined;
      try{
        const closed=context.close();
        await Promise.race([closed,new Promise<void>((_,reject)=>{
          timer=setTimeout(()=>reject(new Error('Истекло время ожидания отключения микрофона')),1000);
        })]);
      }catch(e){error??=e;}finally{clearTimeout(timer);}
    }
    if(error)throw error;
  }
}
