package local.voicedeck;

import ai.onnxruntime.*;
import ai.djl.huggingface.tokenizers.HuggingFaceTokenizer;
import io.vertx.core.json.JsonObject;
import java.nio.file.*;
import java.util.*;
import java.lang.reflect.*;

/** Local-only models. Native sherpa jars are supplied alongside the application. */
public final class Models implements AutoCloseable {
    private final JsonObject config;
    private final Object partial, finals;
    private final OrtEnvironment ort;
    private final OrtSession frida;
    private final HuggingFaceTokenizer tokenizer;
    public final boolean live;
    public Models(boolean live) throws Exception {
        this.live=live;
        if(!live){config=new JsonObject();partial=finals=null;ort=null;frida=null;tokenizer=null;return;}
        config=new JsonObject(Files.readString(Path.of(Main.env("MODEL_CONFIG","models/config.json"))));
        partial=recognizer(config.getJsonObject("partial"));
        finals=config.containsKey("final")?recognizer(config.getJsonObject("final")):partial;
        String embedding=config.getString("embeddingModel",config.getString("fridaModel",""));
        if(!embedding.isBlank()) {
            ort=OrtEnvironment.getEnvironment();
            try(var options=new OrtSession.SessionOptions()) {
                options.setIntraOpNumThreads(config.getInteger("threads",2));
                frida=ort.createSession(embedding,options);
            }
            tokenizer=HuggingFaceTokenizer.newInstance(Path.of(config.getString("embeddingTokenizer",config.getString("fridaTokenizer"))),Map.of("maxLength","512","truncation","true"));
        } else {ort=null;frida=null;tokenizer=null;}
        // Fail readiness on missing/incompatible files, including VAD, before accepting a microphone.
        Object vad=newVad();call(vad,"acceptWaveform",new float[512]);call(vad,"release");
        for(int i=0;i<2;i++){decode(new float[16000],false);decode(new float[16000],true);embed("Проверка готовности распознавания речи.");}
    }
    static Object call(Object target,String method,Object... args) throws Exception {
        for(Method m:target.getClass().getMethods()) {
            if(!m.getName().equals(method)||m.getParameterCount()!=args.length) continue;
            try{return m.invoke(target,args);}catch(IllegalArgumentException ignored){}
        }
        throw new NoSuchMethodException(target.getClass().getName()+"."+method);
    }
    static Object build(String name,Map<String,Object> settings) throws Exception {
        Class<?> cls=Class.forName("com.k2fsa.sherpa.onnx."+name);
        Object builder=cls.getMethod("builder").invoke(null);
        for(var e:settings.entrySet())call(builder,"set"+e.getKey(),e.getValue());
        return call(builder,"build");
    }
    private Object recognizer(JsonObject c) throws Exception {
        if(c==null)throw new IllegalArgumentException("Missing partial model configuration");
        Map<String,Object> model=new LinkedHashMap<>();
        String type=c.getString("type","nemo_ctc");
        if(type.equals("nemo_ctc")) model.put("Nemo",build("OfflineNemoEncDecCtcModelConfig",Map.of("Model",c.getString("model"))));
        else if(type.equals("transducer")) model.put("Transducer",build("OfflineTransducerModelConfig",Map.of("Encoder",c.getString("encoder"),"Decoder",c.getString("decoder"),"Joiner",c.getString("joiner"))));
        else throw new IllegalArgumentException("Unsupported ASR model type: "+type);
        model.put("Tokens",c.getString("tokens"));model.put("NumThreads",config.getInteger("threads",2));model.put("Provider",config.getString("provider","cpu"));model.put("Debug",false);
        Object mc=build("OfflineModelConfig",model);
        Object rc=build("OfflineRecognizerConfig",Map.of("OfflineModelConfig",mc,"DecodingMethod","greedy_search"));
        return Class.forName("com.k2fsa.sherpa.onnx.OfflineRecognizer").getConstructor(rc.getClass()).newInstance(rc);
    }
    public Object newVad() throws Exception {
        Object sc=build("SileroVadModelConfig",Map.of("Model",config.getString("vad"),"Threshold",0.5f,"MinSilenceDuration",0.35f,"MinSpeechDuration",0.25f,"WindowSize",512,"MaxSpeechDuration",20f));
        Object vc=build("VadModelConfig",Map.of("SileroVadModelConfig",sc,"SampleRate",16000,"NumThreads",1,"Provider","cpu","Debug",false));
        return Class.forName("com.k2fsa.sherpa.onnx.Vad").getConstructor(vc.getClass()).newInstance(vc);
    }
    public synchronized String decode(float[] samples,boolean fin) throws Exception {
        Object recognizer=fin?finals:partial, stream=call(recognizer,"createStream");
        try{call(stream,"acceptWaveform",samples,16000);call(recognizer,"decode",stream);return (String)call(call(recognizer,"getResult",stream),"getText");}
        finally{call(stream,"release");}
    }
    public synchronized float[] embed(String text) throws Exception {
        if(frida==null)return null; // Explicit pause/deadline fallback; never fake semantic embeddings.
        boolean mean=config.getString("embeddingPooling","cls").equals("mean");
        var encoding=tokenizer.encode(config.getString("embeddingPrefix",mean?"":"categorize_topic: ")+text);
        long[] ids=Arrays.copyOf(encoding.getIds(),Math.min(512,encoding.getIds().length));
        long[] mask=new long[ids.length];Arrays.fill(mask,1);
        try(var input=OnnxTensor.createTensor(ort,new long[][]{ids});var attention=OnnxTensor.createTensor(ort,new long[][]{mask});var types=OnnxTensor.createTensor(ort,new long[][]{new long[ids.length]})) {
            Map<String,OnnxTensor> inputs=new HashMap<>(Map.of("input_ids",input,"attention_mask",attention));
            if(frida.getInputNames().contains("token_type_ids"))inputs.put("token_type_ids",types);
            try(var output=frida.run(inputs)) {
            Object value=output.get(0).getValue();
            float[] vector=value instanceof float[][][] hidden?hidden[0][0].clone():((float[][])value)[0].clone();
            if(mean&&value instanceof float[][][] hidden){Arrays.fill(vector,0);for(float[] token:hidden[0])for(int i=0;i<vector.length;i++)vector[i]+=token[i]/hidden[0].length;}
            double norm=0;for(float x:vector)norm+=x*x;
            if(norm>0)for(int i=0;i<vector.length;i++)vector[i]/=(float)Math.sqrt(norm);
            return vector;
            }
        }
    }
    public String embeddingStatus(){return frida==null?"pause-only":config.getString("embeddingName","frida");}
    public void close() throws Exception {
        if(partial!=null)call(partial,"release");if(finals!=null&&finals!=partial)call(finals,"release");
        if(frida!=null)frida.close();if(tokenizer!=null)tokenizer.close();
    }
}
