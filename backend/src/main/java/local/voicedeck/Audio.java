package local.voicedeck;

import java.nio.*;
import java.util.*;

/** Per-session 32 ms frames and bounded 20 s ring. Runs on a dedicated serial worker. */
public final class Audio implements AutoCloseable {
    public record Packet(long seq,long offset,float[] samples) {
        public static Packet parse(byte[] bytes) {
            if(bytes.length!=16+512*2)throw new IllegalArgumentException("Expected 1040 bytes: uint64 seq, uint64 sample offset, 512 PCM16 samples");
            ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
            long seq=b.getLong(),offset=b.getLong();
            if(seq<1||offset<0||offset>Long.MAX_VALUE-512)throw new IllegalArgumentException("Invalid audio sequence or offset");
            float[] f=new float[512];for(int i=0;i<512;i++)f[i]=b.getShort()/32768f;
            return new Packet(seq,offset,f);
        }
    }
    public interface Listener {
        void partial(String text,long t0,long t1);
        void finish(String text,long t0,long t1);
        void warning(String message);
    }
    private final Models models;
    private final Listener listener;
    private final Object vad;
    private final float[] ring=new float[16000*20];
    private long samples,phraseStart=-1,lastPartial,baseOffset=-1,lastEditorEnd;
    private String previous="",partial="";
    private boolean overlap;
    private boolean editorMode;
    public void editorMode(boolean enabled){editorMode=enabled;}
    public Audio(Models models,Listener listener) throws Exception {this.models=models;this.listener=listener;vad=models.newVad();}
    public void accept(Packet p) throws Exception {
        if(baseOffset<0)baseOffset=p.offset();
        for(float f:p.samples())ring[(int)(samples++%ring.length)]=f;
        Models.call(vad,"acceptWaveform",p.samples());
        if((boolean)Models.call(vad,"isSpeechDetected")&&phraseStart<0)phraseStart=Math.max(0,samples-4096);
        if(!editorMode&&phraseStart>=0&&samples-lastPartial>=16000&&(boolean)Models.call(vad,"empty")){
            lastPartial=samples;
            try {partial=models.decode(slice(Math.max(phraseStart,samples-160000),samples),false);listener.partial(partial,ms(phraseStart),ms(samples));}
            catch(Exception e){listener.warning("Партиальное распознавание недоступно");}
        }
        drainVad();
        if(!editorMode&&phraseStart>=0&&samples-phraseStart>=16000*8){
            finish(slice(phraseStart,samples),phraseStart,samples);
            phraseStart=samples-32000;overlap=true;
        }
    }
    private void drainVad() throws Exception {
        while(!(boolean)Models.call(vad,"empty")) {
            Object segment=Models.call(vad,"front");
            float[] f=(float[])Models.call(segment,"getSamples");
            long start=((Number)Models.call(segment,"getStart")).longValue();
            long end=start+f.length;
            if(editorMode){
                long originalEnd=end;
                long bufferedStart=editorSegmentStart(start,lastEditorEnd,samples,ring.length);
                long bufferedEnd=Math.min(samples,end+2560);
                if(bufferedStart<=start){start=bufferedStart;end=bufferedEnd;f=slice(start,end);}
                lastEditorEnd=originalEnd;
            }
            // VAD's completed segment has the authoritative start. Editor commands
            // never use partial-window overlap; cropping to its estimate loses verbs.
            int skip=completedSegmentSkip(editorMode,start,phraseStart,f.length);
            if(skip>0){f=Arrays.copyOfRange(f,skip,f.length);start+=skip;}
            if(f.length>0)finish(f,start,end);
            Models.call(vad,"pop");phraseStart=-1;overlap=false;
        }
    }
    static int completedSegmentSkip(boolean editorMode,long start,long phraseStart,int length){
        return !editorMode&&phraseStart>=0&&start<phraseStart?(int)Math.min(length,phraseStart-start):0;
    }
    static long editorSegmentStart(long start,long previousEnd,long samples,int capacity){
        return Math.max(Math.max(0,previousEnd),Math.max(samples-capacity,start-3200));
    }
    private long ms(long sample){return (baseOffset+sample)/16;}
    private float[] slice(long from,long to){from=Math.max(from,to-ring.length);float[] out=new float[(int)(to-from)];for(int i=0;i<out.length;i++)out[i]=ring[(int)((from+i)%ring.length)];return out;}
    private void finish(float[] f,long from,long to)throws Exception {
        String text;
        try{text=models.decode(f,true);}catch(Exception e){
            text=editorMode?"":partial;
            listener.warning(editorMode?"Распознавание не завершено. Команда не выполнена; повторите после переподключения микрофона.":"Финальная модель недоступна; используется последний партиал без нормализации");
        }
        if(overlap)text=Text.deduplicate(previous,text);
        if(!text.isBlank()){listener.finish(text,ms(from),ms(to));previous=text;}
        partial="";
    }
    public void flush()throws Exception{
        if(editorMode){Models.call(vad,"flush");drainVad();}
        else if(phraseStart>=0)finish(slice(phraseStart,samples),phraseStart,samples);
        phraseStart=-1;Models.call(vad,"reset");baseOffset=-1;samples=0;lastPartial=0;lastEditorEnd=0;overlap=false;
    }
    public void close()throws Exception{Models.call(vad,"release");Arrays.fill(ring,0);}
}
