// Stateful low-pass FIR and fractional clock: 44.1/48/96 kHz -> 16 kHz.
class PcmProcessor extends AudioWorkletProcessor {
  constructor(){
    super();this.history=new Float32Array(63);this.pos=0;this.phase=0;this.frame=new Int16Array(512);this.index=0;
    this.taps=new Float32Array(63);let sum=0;const cutoff=Math.min(.45,7200/sampleRate);
    for(let i=0;i<63;i++){const x=i-31;const sinc=x===0?2*cutoff:Math.sin(2*Math.PI*cutoff*x)/(Math.PI*x);const w=.54-.46*Math.cos(2*Math.PI*i/62);this.taps[i]=sinc*w;sum+=this.taps[i];}
    for(let i=0;i<63;i++)this.taps[i]/=sum;
  }
  process(inputs){
    const channel=inputs[0]?.[0];if(!channel)return true;
    for(const sample of channel){
      this.history[this.pos]=sample;this.pos=(this.pos+1)%63;this.phase+=16000;
      if(this.phase>=sampleRate){
        this.phase-=sampleRate;let filtered=0;
        for(let i=0;i<63;i++)filtered+=this.taps[i]*this.history[(this.pos+62-i)%63];
        const x=Math.max(-1,Math.min(1,filtered));this.frame[this.index++]=Math.round(x*(x<0?32768:32767));
        if(this.index===512){this.port.postMessage(this.frame.buffer,[this.frame.buffer]);this.frame=new Int16Array(512);this.index=0;}
      }
    }
    return true;
  }
}
registerProcessor('pcm16',PcmProcessor);
