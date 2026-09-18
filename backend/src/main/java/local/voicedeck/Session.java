package local.voicedeck;

import io.vertx.core.http.ServerWebSocket;
import io.vertx.core.json.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/** All durable state mutations are serialized; model work never runs on the event loop. */
public final class Session implements AutoCloseable {
    final String id,mode;
    final Store store;
    final Models models;
    final Llm llm;
    final boolean sketch=Main.env("SLIDE_MODE","sketch").equals("sketch");
    final ThreadPoolExecutor state=worker("state",512), audioWorker=worker("audio",1000);
    final ThreadPoolExecutor inference=worker("embedding",64);
    final Map<String,JsonObject> sentences=new LinkedHashMap<>(),chunks=new LinkedHashMap<>(),slides=new LinkedHashMap<>();
    final List<String> pending=new ArrayList<>();
    final Map<String,float[]> embeddings=new HashMap<>();
    final Set<String> slideEligible=new HashSet<>();
    final ArrayDeque<Long> latencies=new ArrayDeque<>();
    final ScheduledExecutorService clock=Executors.newSingleThreadScheduledExecutor(Thread.ofVirtual().factory());
    volatile ServerWebSocket socket;
    volatile long seq, audioSeq, audioOffset, lastAccess=System.currentTimeMillis();
    volatile boolean closed;
    long epoch=System.currentTimeMillis(),lastFinalWall,committedAt,lastSlideEnd=-45000,retryAt;
    boolean generating,curating,stopped;
    Audio audio;
    public Session(String id,String mode,Store store,Models models,Llm llm)throws Exception {
        this.id=id;this.mode=mode;this.store=store;this.models=models;this.llm=llm;
        for(JsonObject e:store.events(id,0)){apply(e);seq=e.getLong("seq");}
        if(!sentences.isEmpty())audioOffset=sentences.values().stream().mapToLong(s->s.getLong("t1")*16).max().orElse(0);
        lastFinalWall=System.currentTimeMillis();
        for(JsonObject slide:slides.values())if(slide.getValue("title")!=null){JsonObject c=chunks.get(slide.getString("chunk_id"));if(c!=null)lastSlideEnd=Math.max(lastSlideEnd,c.getLong("t0"));}
        if(!pending.isEmpty())submit(()->commit("recovered"));
        clock.scheduleAtFixedRate(()->submit(this::tick),100,100,TimeUnit.MILLISECONDS);
        clock.scheduleAtFixedRate(()->submit(this::curate),20,20,TimeUnit.SECONDS);
    }
    private static ThreadPoolExecutor worker(String name,int size) {
        return new ThreadPoolExecutor(1,1,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(size),Thread.ofVirtual().name(name+"-",0).factory(),new ThreadPoolExecutor.AbortPolicy());
    }
    void submit(Runnable task){if(closed)return;try{state.execute(()->{try{task.run();}catch(Exception e){warning("Операция не завершена: "+e.getMessage());}});}catch(RejectedExecutionException e){if(socket!=null)socket.close((short)1013,"Session overloaded; reconnect");}}
    void wire(JsonObject e){ServerWebSocket ws=socket;if(ws==null||ws.isClosed())return;if(ws.writeQueueFull()){ws.close((short)1013,"Replay required");return;}ws.writeTextMessage(e.encode());}
    void warning(String text){wire(new JsonObject().put("type","warning").put("message",text));}
    void event(String type,JsonObject data){
        JsonObject e=data.copy().put("type",type).put("session_id",id).put("seq",seq+1).put("emitted_at",System.currentTimeMillis());
        try{store.append(id,e);}catch(Exception ex){throw new IllegalStateException("Не удалось сохранить событие; повторите после восстановления БД",ex);}
        apply(e);seq++;wire(e);
    }
    void apply(JsonObject e){
        switch(e.getString("type")) {
            case "final" -> {JsonObject s=e.getJsonObject("sentence");sentences.put(s.getString("id"),s);pending.add(s.getString("id"));}
            case "chunk" -> {JsonObject c=e.getJsonObject("chunk");chunks.put(c.getString("id"),c);pending.removeAll(c.getJsonArray("sentence_ids").getList());}
            case "chunk_revise" -> {
                for(Object key:e.getJsonArray("replace_ids")){chunks.remove(key.toString());slides.remove(key.toString());}
                for(Object raw:e.getJsonArray("chunks")){JsonObject c=raw instanceof JsonObject j?j:new JsonObject((Map<String,Object>)raw);chunks.put(c.getString("id"),c);}
            }
            case "slide" -> {JsonObject s=e.getJsonObject("slide"),c=chunks.get(s.getString("chunk_id"));if(c!=null&&c.getInteger("rev").equals(s.getInteger("rev"))){slides.put(s.getString("chunk_id"),s);if(s.getValue("title")!=null)slideEligible.add(s.getString("chunk_id"));}}
            case "stopped" -> stopped=true;
            default -> {}
        }
    }
    void attach(ServerWebSocket ws,long from){submit(()->{
        if(from<0||from>seq){ws.close((short)1008,"Invalid replay cursor");return;}
        if(socket!=null&&socket!=ws)socket.close((short)1000,"Replaced by another connection");
        socket=ws;lastAccess=System.currentTimeMillis();
        try{for(JsonObject e:store.events(id,from))wire(e);}catch(Exception e){ws.close((short)1011,"Replay unavailable");return;}
        wire(new JsonObject().put("type","ready").put("seq",seq).put("audio_seq",audioSeq).put("audio_offset",audioOffset).put("mode",mode).put("stopped",stopped));
    });}
    void text(JsonObject message){submit(()->{
        lastAccess=System.currentTimeMillis();
        String type=message.getString("type","");
        if(type.equals("text")&&mode.equals("demo")) {
            if(!message.fieldNames().equals(Set.of("type","text")))throw new IllegalArgumentException("Unexpected text fields");
            String text=message.getString("text","").strip();
            if(text.isEmpty()||text.length()>16000)throw new IllegalArgumentException("Текст: от 1 до 16000 символов");
            long t0=audioOffset/16,t1=t0+Math.max(1000,Text.words(text)*350L);
            epoch=System.currentTimeMillis()-t1;audioOffset=t1*16;
            wire(new JsonObject().put("type","partial").put("text",text));
            acceptFinal(text,t0,t1);return;
        }
        if(type.equals("flush")){flush(false);return;}
        if(type.equals("stop")){flush(true);return;}
        if(type.equals("revise")) {revise(message);return;}
        throw new IllegalArgumentException("Unknown command or incompatible mode");
    });}
    void acceptAudio(byte[] bytes){
        if(!mode.equals("live")){warning("Микрофон доступен только в режиме live с установленными моделями");return;}
        final Audio.Packet p;
        try{p=Audio.Packet.parse(bytes);}catch(Exception e){warning(e.getMessage());return;}
        submit(()->{
            lastAccess=System.currentTimeMillis();
            if(p.seq()<=audioSeq){wire(new JsonObject().put("type","audio_ack").put("audio_seq",audioSeq));return;}
            if(p.seq()!=audioSeq+1||p.offset()!=audioOffset){wire(new JsonObject().put("type","audio_resync").put("audio_seq",audioSeq).put("audio_offset",audioOffset));return;}
            if(audioWorker.getQueue().remainingCapacity()==0){warning("Аудиобуфер заполнен; запись приостановлена");if(socket!=null)socket.close((short)1013,"Audio backpressure");return;}
            if(stopped||audioSeq==0){epoch=System.currentTimeMillis()-p.offset()/16;stopped=false;}
            audioSeq=p.seq();audioOffset=p.offset()+512;
            audioWorker.execute(()->{
                try {
                    if(audio==null)audio=new Audio(models,new Audio.Listener(){
                        public void partial(String text,long t0,long t1){submit(()->{Metrics.observe("partial_latency",System.currentTimeMillis()-epoch-t1);wire(new JsonObject().put("type","partial").put("text",text).put("t0",t0).put("t1",t1));});}
                        public void finish(String text,long t0,long t1){submit(()->acceptFinal(text,t0,t1));}
                        public void warning(String text){submit(()->Session.this.warning(text));}
                    });
                    audio.accept(p);
                    submit(()->wire(new JsonObject().put("type","audio_ack").put("audio_seq",p.seq())));
                }catch(Exception e){submit(()->warning("Ошибка аудиомодели: "+e.getMessage()));}
            });
        });
    }
    void acceptFinal(String text,long t0,long t1){
        Metrics.observe("final_latency",System.currentTimeMillis()-epoch-t1);
        if(sentences.size()>=20000)throw new IllegalStateException("Лимит сессии достигнут; начните новую");
        List<String> list=Text.sentences(text);long total=Math.max(1,text.length()),cursor=t0;
        for(int i=0;i<list.size();i++){
            String sentence=list.get(i);long end=i==list.size()-1?t1:Math.min(t1,cursor+(t1-t0)*sentence.length()/total);
            var s=new JsonObject().put("id",UUID.randomUUID().toString()).put("text",sentence).put("t0",cursor).put("t1",end);
            event("final",new JsonObject().put("sentence",s));cursor=end;
            try{inference.execute(()->{try{long start=System.nanoTime();float[] vector=models.embed(sentence);Metrics.observe("embedding_inference",TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start));submit(()->{embeddings.put(s.getString("id"),vector);semantic(s.getString("id"));});try{store.embedding(id,s.getString("id"),vector);}catch(Exception e){submit(()->warning("Эмбеддинг не сохранён в БД"));}}catch(Exception e){submit(()->warning("FRIDA недоступна: используются паузы и дедлайн"));}});}catch(RejectedExecutionException e){warning("Очередь FRIDA заполнена: используются паузы и дедлайн");}
            if(pending.stream().map(sentences::get).mapToInt(v->Text.words(v.getString("text"))).sum()>=500)commit("size");
        }
        lastFinalWall=System.currentTimeMillis();
    }
    void semantic(String sid){
        int at=pending.indexOf(sid);if(at<0){coalesce();return;}if(at<1)return;
        float[] vector=embeddings.get(sid);if(vector==null)return;
        double sum=0,weights=0;for(int i=Math.max(0,at-5);i<at;i++){float[] old=embeddings.get(pending.get(i));if(old!=null){double w=1.0/(at-i);sum+=w*Text.cosine(old,vector);weights+=w;}}
        int words=pending.subList(0,at).stream().map(sentences::get).mapToInt(s->Text.words(s.getString("text"))).sum();
        if(weights>0&&sum/weights<0.3&&words>=50)commitIds(new ArrayList<>(pending.subList(0,at)),"drift");
    }
    void tick(){
        long now=System.currentTimeMillis();
        if(!pending.isEmpty()) {
            long end=sentences.get(pending.getLast()).getLong("t1");
            if(now-(epoch+end)>=2000||now-lastFinalWall>=1200)commit("deadline");
        }
        generate();
    }
    JsonObject chunk(List<String> ids,String id,int rev,String status){
        return new JsonObject().put("id",id).put("rev",rev).put("status",status).put("sentence_ids",new JsonArray(ids))
            .put("text",String.join(" ",ids.stream().map(sentences::get).map(s->s.getString("text")).toList()))
            .put("t0",sentences.get(ids.getFirst()).getLong("t0")).put("t1",sentences.get(ids.getLast()).getLong("t1")).put("updated_at",System.currentTimeMillis());
    }
    void commit(String reason){if(!pending.isEmpty())commitIds(new ArrayList<>(pending),reason);}
    void commitIds(List<String> ids,String reason){
        JsonObject c=chunk(ids,UUID.randomUUID().toString(),1,"provisional");
        long latency=Math.max(0,System.currentTimeMillis()-(epoch+c.getLong("t1")));
        event("chunk",new JsonObject().put("chunk",c).put("reason",reason).put("latency_ms",latency));
        Metrics.observe("chunk_latency",latency);
        latencies.add(latency);if(latencies.size()>1000)latencies.removeFirst();committedAt=System.currentTimeMillis();
        if(mode.equals("live"))coalesce();
    }
    void coalesce(){
        if(!mode.equals("live"))return;
        var ordered=orderedChunks();if(ordered.size()<2)return;
        var a=ordered.get(ordered.size()-2);var b=ordered.getLast();
        if(!a.getString("status").equals("provisional")||!b.getString("status").equals("provisional"))return;
        if(System.currentTimeMillis()-a.getLong("updated_at")>180000||b.getLong("t0")-a.getLong("t1")>1800||b.getLong("t1")-a.getLong("t0")>60000)return;
        if(Text.words(a.getString("text"))>=50||Text.words(a.getString("text"))+Text.words(b.getString("text"))>120)return;
        List<String> left=a.getJsonArray("sentence_ids").getList(),right=b.getJsonArray("sentence_ids").getList();
        float[] av=embeddings.get(left.getLast()),bv=embeddings.get(right.getFirst());
        boolean continuation=!a.getString("text").matches("(?s).*[.!?…][»\"]?$"),related=av!=null&&bv!=null&&Text.cosine(av,bv)>.5;
        if(!continuation&&!related)return;
        List<String> ids=new ArrayList<>(left);ids.addAll(right);
        event("chunk_revise",new JsonObject().put("operation","merge").put("replace_ids",new JsonArray().add(a.getString("id")).add(b.getString("id"))).put("chunks",new JsonArray().add(chunk(ids,a.getString("id"),a.getInteger("rev")+1,"provisional"))));
    }
    void flush(boolean stop){
        if(mode.equals("live"))audioWorker.execute(()->{try{if(audio!=null)audio.flush();}catch(Exception e){submit(()->warning("Не удалось завершить аудиофразу"));}submit(()->finishFlush(stop));});
        else finishFlush(stop);
    }
    void finishFlush(boolean stop){commit("flush");if(stop){event("stopped",new JsonObject());}wire(new JsonObject().put("type","flushed"));}
    List<JsonObject> orderedChunks(){return chunks.values().stream().sorted(Comparator.comparingLong(c->c.getLong("t0"))).toList();}
    void revise(JsonObject m){
        if(!m.fieldNames().equals(Set.of("type","operation","chunk_id","rev","split_at")))throw new IllegalArgumentException("Invalid revision fields");
        JsonObject c=chunks.get(m.getString("chunk_id"));if(c==null)return;
        int rev=m.getInteger("rev");if(rev<=c.getInteger("rev"))return;
        if(rev!=c.getInteger("rev")+1)throw new IllegalArgumentException("Revision conflict; refresh state");
        if(System.currentTimeMillis()-c.getLong("updated_at")>180000){warning("Окно ревизии 3 минуты истекло");return;}
        String op=m.getString("operation");List<String> ids=new ArrayList<>(c.getJsonArray("sentence_ids").getList());
        JsonArray replaced=new JsonArray().add(c.getString("id")),updated=new JsonArray();
        switch(op){
            case "confirm" -> updated.add(chunk(ids,c.getString("id"),rev,"confirmed"));
            case "split" -> {int at=m.getInteger("split_at",-1);if(at<1||at>=ids.size())throw new IllegalArgumentException("Invalid split index");updated.add(chunk(ids.subList(0,at),c.getString("id"),rev,"confirmed"));updated.add(chunk(ids.subList(at,ids.size()),UUID.randomUUID().toString(),1,"confirmed"));}
            case "merge" -> {var ordered=orderedChunks();int at=ordered.indexOf(c);if(at==ordered.size()-1)throw new IllegalArgumentException("Нет следующего куска");var next=ordered.get(at+1);if(System.currentTimeMillis()-next.getLong("updated_at")>180000)throw new IllegalArgumentException("Окно ревизии истекло");ids.addAll(next.getJsonArray("sentence_ids").getList());if(ids.stream().map(sentences::get).mapToInt(s->Text.words(s.getString("text"))).sum()>500)throw new IllegalArgumentException("Слияние превысит 500 слов");replaced.add(next.getString("id"));updated.add(chunk(ids,c.getString("id"),rev,"confirmed"));}
            default -> throw new IllegalArgumentException("Unknown revision operation");
        }
        event("chunk_revise",new JsonObject().put("operation",op).put("replace_ids",replaced).put("chunks",updated));
    }
    void generate(){
        if(generating||curating||System.currentTimeMillis()<retryAt)return;
        JsonObject candidate=orderedChunks().stream().filter(c->!slides.containsKey(c.getString("id"))).findFirst().orElse(null);if(candidate==null)return;
        // Store an explicit skipped entry for quota, so old chunks never starve later ones.
        if(!sketch&&!slideEligible.contains(candidate.getString("id"))&&candidate.getLong("t0")<lastSlideEnd+45000&&lastSlideEnd>=0){event("slide",new JsonObject().put("slide",new JsonObject().put("chunk_id",candidate.getString("id")).put("rev",candidate.getInteger("rev")).put("title",null).put("bullets",new JsonArray()).put("notes","").put("source","quota")));return;}
        generating=true;JsonObject c=candidate.copy();
        Thread.startVirtualThread(()->{
            try{var s=sketch||mode.equals("demo")?Llm.extractive(c.getString("text")):llm.slide(c.getString("text"));submit(()->{
                try{var current=chunks.get(c.getString("id"));if(current!=null&&current.getInteger("rev").equals(c.getInteger("rev"))){s.put("chunk_id",c.getString("id")).put("rev",c.getInteger("rev")).put("t0",c.getLong("t0")).put("t1",c.getLong("t1")).put("source",sketch?"sketch":mode.equals("demo")?"extractive-demo":"local-llm");event("slide",new JsonObject().put("slide",s));if(s.getValue("title")!=null)lastSlideEnd=c.getLong("t0");}}finally{generating=false;}
            });}catch(Exception e){submit(()->{generating=false;retryAt=System.currentTimeMillis()+10000;warning("Локальная LLM недоступна: слайды будут дополнены после восстановления");});}
        });
    }
    void curate(){
        if(sketch||mode.equals("demo")||curating||generating)return;
        List<JsonObject> recent=orderedChunks().stream().filter(c->System.currentTimeMillis()-c.getLong("updated_at")<180000&&c.getString("status").equals("provisional")).toList();
        if(recent.isEmpty())return;
        JsonObject c=recent.getFirst();List<String> ids=c.getJsonArray("sentence_ids").getList();if(ids.size()<2||ids.size()>25)return;
        curating=true;List<String> texts=ids.stream().map(sentences::get).map(s->s.getString("text")).toList();
        Thread.startVirtualThread(()->{try{var boundaries=llm.boundaries(texts);submit(()->{try{JsonObject current=chunks.get(c.getString("id"));if(current!=null&&current.getInteger("rev").equals(c.getInteger("rev")))revise(new JsonObject().put("type","revise").put("operation",boundaries.isEmpty()?"confirm":"split").put("chunk_id",c.getString("id")).put("rev",c.getInteger("rev")+1).put("split_at",boundaries.isEmpty()?0:boundaries.getFirst()));}finally{curating=false;}});}catch(Exception e){submit(()->curating=false);}});
    }
    JsonObject metrics(){long[] sorted=latencies.stream().mapToLong(Long::longValue).sorted().toArray();return new JsonObject().put("type","metrics").put("current_ms",latencies.isEmpty()?0:latencies.getLast()).put("p95_ms",sorted.length==0?0:sorted[(int)Math.ceil(sorted.length*.95)-1]).put("chunks",chunks.size()).put("sentences",sentences.size()).put("audio_queue",audioWorker.getQueue().size()).put("mode",mode);}
    void snapshot(Consumer<JsonObject> cb){submit(()->cb.accept(new JsonObject().put("session_id",id).put("seq",seq).put("sentences",new JsonArray(new ArrayList<>(sentences.values()))).put("chunks",new JsonArray(orderedChunks())).put("slides",new JsonArray(new ArrayList<>(slides.values()))).put("metrics",metrics())));}
    public void close(){closed=true;clock.shutdownNow();state.shutdown();audioWorker.shutdown();inference.shutdown();if(socket!=null)socket.close();Thread.startVirtualThread(()->{try{audioWorker.awaitTermination(30,TimeUnit.SECONDS);if(audio!=null)audio.close();}catch(Exception ignored){}});}
}
