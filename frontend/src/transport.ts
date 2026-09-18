import {Event} from './store';
export type Credentials={id:string;token:string;mode:string};
export class Transport {
  ws?:WebSocket;closed=false;timer?:ReturnType<typeof setTimeout>;attempt=0;ready=false;
  audioSeq=0;offset=0;packets=new Map<number,ArrayBuffer>();
  constructor(public credentials:Credentials,private cursor:()=>number,private event:(e:Event)=>void,private status:(s:string)=>void,private failure:(s:string)=>void){this.connect();}
  connect(){
    if(this.closed)return;this.status('Подключение');this.ready=false;
    this.ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/session`);
    this.ws.onopen=()=>this.ws?.send(JSON.stringify({type:'auth',session_id:this.credentials.id,token:this.credentials.token,from:this.cursor()}));
    this.ws.onmessage=({data})=>{
      try{
        const e=JSON.parse(data);
        if(e.type==='ready'){
          if(e.seq!==this.cursor())throw new Error('История сессии рассинхронизирована');
          this.ready=true;this.attempt=0;this.status('Подключено');
          // Server restart loses only volatile audio. Rebase the bounded unacknowledged buffer.
          const restarted=e.audio_seq===0&&this.audioSeq>0;
          const queued=[...this.packets.entries()].filter(([seq])=>restarted||seq>e.audio_seq).map(([,packet])=>packet);
          if(restarted)this.failure('Сервер перезапущен: незафиксированная аудиофраза могла быть потеряна. История текста восстановлена.');
          this.packets.clear();this.audioSeq=e.audio_seq;this.offset=e.audio_offset;
          for(const packet of queued)this.audio(packet.slice(16));
        }else if(e.type==='audio_ack'){for(const seq of this.packets.keys())if(seq<=e.audio_seq)this.packets.delete(seq);}
        else if(e.type==='audio_resync'){this.ws?.close();}
        else this.event(e);
      }catch(error){this.failure(String(error));this.ws?.close();}
    };
    this.ws.onclose=()=>{this.ready=false;if(this.closed)return;this.status('Восстановление связи');this.timer=setTimeout(()=>this.connect(),Math.min(10000,500*2**this.attempt++)+Math.random()*200);};
    this.ws.onerror=()=>this.ws?.close();
  }
  send(data:object){if(!this.ready||this.ws?.readyState!==WebSocket.OPEN)throw new Error('Дождитесь восстановления соединения');this.ws.send(JSON.stringify(data));}
  audio(pcm:ArrayBuffer){
    if(this.packets.size>=938)throw new Error('Буфер звука заполнен (30 секунд). Запись остановлена; восстановите соединение.');
    const packet=new ArrayBuffer(16+pcm.byteLength),view=new DataView(packet);
    view.setBigUint64(0,BigInt(++this.audioSeq),true);view.setBigUint64(8,BigInt(this.offset),true);new Uint8Array(packet,16).set(new Uint8Array(pcm));this.offset+=pcm.byteLength/2;
    this.packets.set(this.audioSeq,packet);
    if(this.ready&&this.ws?.readyState===WebSocket.OPEN&&this.ws.bufferedAmount<1024*1024)this.ws.send(packet);
    else if(this.ready)this.ws?.close();
  }
  close(){this.closed=true;clearTimeout(this.timer);this.ws?.close();}
}
export class Microphone {
  context?:AudioContext;stream?:MediaStream;node?:AudioWorkletNode;
  async start(frame:(pcm:ArrayBuffer)=>void,fail:(message:string)=>void){
    try{
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
      this.context=new AudioContext();await this.context.audioWorklet.addModule('/pcm-worklet.js');
      this.node=new AudioWorkletNode(this.context,'pcm16');this.node.port.onmessage=e=>frame(e.data);
      const mute=this.context.createGain();mute.gain.value=0;
      this.context.createMediaStreamSource(this.stream).connect(this.node);this.node.connect(mute).connect(this.context.destination);
      this.stream.getAudioTracks()[0].onended=()=>fail('Микрофон отключён. Подключите устройство и возобновите запись.');
      this.context.onstatechange=()=>{if(this.context?.state==='suspended')fail('Аудиоконтекст приостановлен. Возобновите запись кнопкой.');};
      await this.context.resume();
    }catch(e){await this.stop();throw e;}
  }
  async stop(){if(this.node)this.node.port.onmessage=null;this.stream?.getTracks().forEach(t=>t.stop());if(this.context){this.context.onstatechange=null;await this.context.close();}this.context=undefined;this.stream=undefined;}
}
