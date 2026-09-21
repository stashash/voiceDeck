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
    // T-S3/T1b: depth-score EMA state (mutated only on the state worker thread); depth is computed before the EMA update.
    double emaBaseline=0.0,emaDispersion=0.0;long emaCount=0;
    // T1b: stream-level boundary detector state (state worker only): valley-confirmation candidate.
    final boolean semanticDebug=Main.env("SEMANTIC_DEBUG","false").equalsIgnoreCase("true");
    final List<String> streamIds=new ArrayList<>();
    String candidateSid;double candidateDepth,candidateCos;int candidateAge;
    // T4: bilateral TextTiling-style rolling buffer of the last K sentence vectors (state worker only).
    // The buffer drops oldest entries, so gap[i] is always evaluated within a recent window.
    final List<String> rollingIds=new ArrayList<>();
    final List<float[]> rollingVecs=new ArrayList<>();
    Audio audio;
    public Session(String id,String mode,Store store,Models models,Llm llm)throws Exception {
        this.id=id;this.mode=mode;this.store=store;this.models=models;this.llm=llm;
        for(JsonObject e:store.events(id,0)){apply(e);seq=e.getLong("seq");}
        // T-S4: restore embeddings from pgvector so semantic() works after restart.
        if(store.durable())try{embeddings.putAll(store.embeddingsOf(id));}catch(Exception ex){System.err.println("Embeddings restore failed for "+id+": "+ex.getMessage());}
        if(!sentences.isEmpty())audioOffset=sentences.values().stream().mapToLong(s->s.getLong("t1")*16).max().orElse(0);
        lastFinalWall=System.currentTimeMillis();
        for(JsonObject slide:slides.values())if(slide.getValue("title")!=null){JsonObject c=chunks.get(slide.getString("chunk_id"));if(c!=null)lastSlideEnd=Math.max(lastSlideEnd,c.getLong("t0"));}
        if(!pending.isEmpty())submit(()->commit("recovered"));
        clock.scheduleAtFixedRate(()->submit(this::tick),100,100,TimeUnit.MILLISECONDS);
        clock.scheduleAtFixedRate(()->submit(this::curate),20,20,TimeUnit.SECONDS);
        clock.scheduleAtFixedRate(()->submit(this::confirmChunkPass),5,5,TimeUnit.SECONDS); // T-S6
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
            case "final" -> {JsonObject s=e.getJsonObject("sentence");sentences.put(s.getString("id"),s);pending.add(s.getString("id"));streamIds.add(s.getString("id"));}
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
            // T-S9: explicit discourse marker at sentence start commits accumulated pending first.
            if(Text.startsWithMarker(sentence)&&!pending.isEmpty()){int w=0;for(String pid:pending)w+=Text.words(sentences.get(pid).getString("text"));if(w>=models.markerMinWords())commit("marker");}
            var s=new JsonObject().put("id",UUID.randomUUID().toString()).put("text",sentence).put("t0",cursor).put("t1",end);
            event("final",new JsonObject().put("sentence",s));cursor=end;
            // T1b: per-sentence embedding — honest sentence vectors feed the stream detector and offline TextTiling.
            String latestSid=s.getString("id");
            try{inference.execute(()->{try{long start=System.nanoTime();float[] vector=models.embed(sentence);Metrics.observe("embedding_inference",TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start));submit(()->{if(vector!=null){embeddings.put(latestSid,vector);detectBoundary(latestSid);}});try{if(vector!=null)store.embedding(id,latestSid,vector);}catch(Exception e){submit(()->warning("Эмбеддинг не сохранён в БД"));}}catch(Exception e){submit(()->warning("Эмбеддинг недоступен: используются паузы и дедлайн"));}});}catch(RejectedExecutionException e){warning("Очередь эмбеддингов заполнена: используются паузы и дедлайн");}
            int words=pending.stream().map(sentences::get).mapToInt(v->Text.words(v.getString("text"))).sum();
            if(words>=models.chunkSizeEmergency())commit("size-emergency"); // T-S5: emergency ceiling, do not commit per-sentence otherwise.
        }
        lastFinalWall=System.currentTimeMillis();
    }
    /** T4: online bilateral TextTiling-style boundary detector over per-sentence vectors.
     *  Rolling buffer of the last K sentence vectors (oldest dropped when > K). For each new embedding:
     *  - gap[i] = 1 - cosine(mean(window_left), mean(window_right)) with half-width w (TextTiling.java-style).
     *  - lateral_depth = max(0, gap[i]-gap[i-1]) + max(0, gap[i]-gap[i+1]) — valley prominence in cosine-distance units.
     *  - Pair-wise cosine (T1b legacy) feeds the EMA; EMA acts as an adaptive cosine-floor hint:
     *    cosine must drop below (emaBaseline - dispersionMultiplier*emaDispersion) for a dip to qualify.
     *  - Depth (= emaBaseline - cosine) is computed BEFORE the EMA update (T1b order fix preserved).
     *  - Cos-floor 0.55 removed from primary path; deepDipCosFloor (default 1.0=off) kept as optional guard.
     *  - Valley confirmation: candidate remembered, confirmed on cosine recovery / replaced by deeper lateral_depth / timed out after 3 flat sentences. */
    void detectBoundary(String sid){
        if(stopped)return;
        int at=streamIds.indexOf(sid);if(at<1)return;
        float[] vector=embeddings.get(sid);if(vector==null)return;

        // T4: rolling buffer (last K sentence vectors). Oldest entry is dropped when buffer grows past K.
        rollingIds.add(sid);
        rollingVecs.add(vector);
        int K=models.rollingBufferSize();
        while(rollingIds.size()>K){rollingIds.remove(0);rollingVecs.remove(0);}
        int n=rollingVecs.size();
        int w=models.bilateralWindow();
        // Latest valid bilateral gap position: rolling buffer must hold indices [idx-w, idx+w), so the
        // freshest fully-known gap is at n-1-w (left fully available, right just filled by this step).
        int latestGapIdx=n-1-w;

        // T1b: pair cosine via streamIds lookup (last embedded vector within 20 back).
        String prevId=null;
        for(int i=at-1;i>=Math.max(0,at-20);i--){if(embeddings.containsKey(streamIds.get(i))){prevId=streamIds.get(i);break;}}
        if(prevId==null)return;
        double cosine=Text.cosine(embeddings.get(prevId),vector);

        double alpha=0.1,depth;
        // T1b EMA-fix: depth (= emaBaseline - cosine) and threshold are captured BEFORE the EMA moves,
        // so the dip is judged against the snapshot that existed when the pair arrived.
        double threshold=Math.max(models.depthFloor(),models.dispersionMultiplier()*emaDispersion);
        if(emaCount==0){depth=0;emaBaseline=cosine;emaDispersion=0.05;emaCount=1;}
        else{
            depth=emaBaseline-cosine; // BEFORE update.
            double dev=Math.abs(cosine-emaBaseline);
            emaBaseline+=alpha*(cosine-emaBaseline);emaDispersion+=alpha*(dev-emaDispersion);emaCount++;
        }

        // T4: bilateral gap and lateral depth (cosine-distance units, valley prominence).
        double bilateralGap=0.0,lateralDepth=0.0;
        if(latestGapIdx>=w+1){
            bilateralGap=Text.bilateralGap(rollingVecs,latestGapIdx,w);
            double leftGap=Text.bilateralGap(rollingVecs,latestGapIdx-1,w);
            double rightGap=Text.bilateralGap(rollingVecs,latestGapIdx+1,w);
            lateralDepth=Math.max(0,bilateralGap-leftGap)+Math.max(0,bilateralGap-rightGap);
        }

        boolean emergency=cosine<models.emergencyThreshold();
        boolean dip=emaCount>=5&&depth>threshold&&cosine<models.deepDipCosFloor();
        String decision="none";
        if(emergency)decision=applyBoundaryAt(sid,true)?"confirmed-boundary":"none";
        else if(dip){
            if(candidateSid==null||depth>candidateDepth){candidateSid=sid;candidateDepth=depth;candidateCos=cosine;candidateAge=0;decision="candidate";}
            else if(cosine>candidateCos)decision=applyCandidate()?"confirmed-boundary":"none";
            else if(++candidateAge>=3)decision=applyCandidate()?"confirmed-boundary":"none";
        }
        else if(candidateSid!=null){
            if(cosine>candidateCos)decision=applyCandidate()?"confirmed-boundary":"none";
            else if(++candidateAge>=3)decision=applyCandidate()?"confirmed-boundary":"none";
        }
        if(semanticDebug)wire(new JsonObject().put("type","semantic_debug")
            .put("sid",sid)
            .put("cosine",cosine)
            .put("depth",depth)
            .put("bilateral_gap",bilateralGap)
            .put("lateral_depth",lateralDepth)
            .put("ema_baseline",emaBaseline)
            .put("ema_dispersion",emaDispersion)
            .put("ema_baseline_distance",1.0-emaBaseline)
            .put("decision",decision));
    }
    /** T1b: a confirmed valley applies the boundary at the remembered candidate, then clears it. */
    boolean applyCandidate(){String sid=candidateSid;candidateSid=null;candidateDepth=0;candidateCos=0;candidateAge=0;return applyBoundaryAt(sid,false);}
    /** T1b: apply a boundary immediately before {@code sid}. Inside pending → drift commit (chunkSizeMin words preserved);
     *  inside the last provisional chunk → revise-split with source "drift" (halves ≥ markerMinWords).
     *  Confirmed chunks and chunk junctions are never touched (arbiter: drift priority 0 < confirmer 1). */
    boolean applyBoundaryAt(String sid,boolean emergency){
        int at=pending.indexOf(sid);
        if(at>0){
            int words=0;for(int i=0;i<at;i++)words+=Text.words(sentences.get(pending.get(i)).getString("text"));
            if(words<models.chunkSizeMin())return false; // no micro-chunks from drift
            commitIds(new ArrayList<>(pending.subList(0,at)),emergency?"drift-emergency":"drift");
            return true;
        }
        if(at==0)return false; // junction pending/committed already carries a boundary.
        var ordered=orderedChunks();if(ordered.isEmpty())return false;
        JsonObject last=ordered.get(ordered.size()-1);
        if(!"provisional".equals(last.getString("status")))return false; // confirmed junctions are not touched.
        List<String> ids=last.getJsonArray("sentence_ids").getList();
        int idx=ids.indexOf(sid);if(idx<1)return false; // chunk start or an older chunk: junction of provisionals needs no split.
        int leftWords=0;for(int i=0;i<idx;i++)leftWords+=Text.words(sentences.get(ids.get(i)).getString("text"));
        int rightWords=0;for(int i=idx;i<ids.size();i++)rightWords+=Text.words(sentences.get(ids.get(i)).getString("text"));
        if(leftWords<models.markerMinWords()||rightWords<models.markerMinWords())return false; // minimal half size for committed splits
        revise(new JsonObject().put("type","revise").put("operation","split").put("source","drift").put("chunk_id",last.getString("id")).put("rev",last.getInteger("rev")+1).put("split_at",idx));
        return true;
    }
    void tick(){
        long now=System.currentTimeMillis();
        if(!pending.isEmpty()) {
            long end=sentences.get(pending.getLast()).getLong("t1");
            int words=pending.stream().map(sentences::get).mapToInt(v->Text.words(v.getString("text"))).sum();
            long sincePhraseEnd=now-(epoch+end);
            long sinceLastFinal=now-lastFinalWall;
            // T-S5/T1a: size-cap (180 words) > sentences-cap (12 sentences) > target (120 words) > deadline (1.2–2 s).
            if(words>=models.chunkSizeMax()&&sinceLastFinal>100)commit("size-cap");
            else if(pending.size()>=models.chunkSentencesMax()&&sinceLastFinal>100)commit("sentences-cap");
            else if(words>=models.chunkSizeTarget()&&sinceLastFinal>=600)commit("size-target");
            else if(sincePhraseEnd>=2000||sinceLastFinal>=1200)commit("deadline");
        }
        generate();
    }
    JsonObject chunk(List<String> ids,String id,int rev,String status,String reason){
        return new JsonObject().put("id",id).put("rev",rev).put("status",status).put("reason",reason).put("sentence_ids",new JsonArray(ids))
            .put("text",String.join(" ",ids.stream().map(sentences::get).map(s->s.getString("text")).toList()))
            .put("t0",sentences.get(ids.getFirst()).getLong("t0")).put("t1",sentences.get(ids.getLast()).getLong("t1")).put("updated_at",System.currentTimeMillis());
    }
    void commit(String reason){if(!pending.isEmpty())commitIds(new ArrayList<>(pending),reason);}
    void commitIds(List<String> ids,String reason){
        JsonObject c=chunk(ids,UUID.randomUUID().toString(),1,"provisional",reason);
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
        if(Text.words(a.getString("text"))>=models.chunkSizeMin()||Text.words(a.getString("text"))+Text.words(b.getString("text"))>models.chunkCoalesceMax())return;
        List<String> left=a.getJsonArray("sentence_ids").getList(),right=b.getJsonArray("sentence_ids").getList();
        float[] av=embeddings.get(left.getLast()),bv=embeddings.get(right.getFirst());
        boolean continuation=!a.getString("text").matches("(?s).*[.!?…][»\"]?$"),related=av!=null&&bv!=null&&Text.cosine(av,bv)>models.coalesceThreshold();
        if(!continuation&&!related)return;
        List<String> ids=new ArrayList<>(left);ids.addAll(right);
        event("chunk_revise",new JsonObject().put("operation","merge").put("source","drift").put("replace_ids",new JsonArray().add(a.getString("id")).add(b.getString("id"))).put("chunks",new JsonArray().add(chunk(ids,a.getString("id"),a.getInteger("rev")+1,"provisional","merge").put("source","drift"))));
    }
    void flush(boolean stop){
        if(mode.equals("live"))audioWorker.execute(()->{try{if(audio!=null)audio.flush();}catch(Exception e){submit(()->warning("Не удалось завершить аудиофразу"));}submit(()->finishFlush(stop));});
        else finishFlush(stop);
    }
    void finishFlush(boolean stop){commit("flush");if(stop){event("stopped",new JsonObject());runOfflinePass();}wire(new JsonObject().put("type","flushed"));}
    /** T-S13: bilateral resegmentation after stop. Skips when any chunk carries human source, when embeddings are sparse, or in demo mode. */
    void runOfflinePass(){
        if(!mode.equals("live"))return;
        if(chunks.values().stream().anyMatch(c->"human".equals(c.getString("source","")))){warning("Офлайн-проход пропущен: есть ручные правки");return;}
        var ordered=sentences.values().stream().sorted(Comparator.comparingLong(s->s.getLong("t0"))).toList();
        List<String> ids=new ArrayList<>();List<float[]> vecs=new ArrayList<>();
        for(var s:ordered){float[] v=embeddings.get(s.getString("id"));if(v!=null){ids.add(s.getString("id"));vecs.add(v);}}
        if(ids.size()<6)return;
        var bounds=TextTiling.boundaries(vecs,2,0.05);
        if(bounds.isEmpty())return;
        // Rebuild segmentation: one atomic chunk_revise replacing every chunk with offline boundaries.
        List<List<String>> groups=new ArrayList<>();int start=0;
        for(int b:bounds){groups.add(new ArrayList<>(ids.subList(start,b)));start=b;}
        groups.add(new ArrayList<>(ids.subList(start,ids.size())));
        groups.removeIf(List::isEmpty);
        if(groups.size()<=1)return;
        JsonArray replaced=new JsonArray(),updated=new JsonArray();
        for(var c:orderedChunks())replaced.add(c.getString("id"));
        for(List<String> g:groups)updated.add(chunk(g,UUID.randomUUID().toString(),1,"confirmed","offline").put("source","offline"));
        event("chunk_revise",new JsonObject().put("operation","offline").put("source","offline").put("replace_ids",replaced).put("chunks",updated));
    }
    List<JsonObject> orderedChunks(){return chunks.values().stream().sorted(Comparator.comparingLong(c->c.getLong("t0"))).toList();}
    /** T-S7: revision arbiter priority. Higher wins; ties allowed. */
    static int sourcePriority(String s){return switch(s==null?"":s){case "human"->4;case "offline"->3;case "curator"->2;case "confirmer"->1;default->0;};}
    void revise(JsonObject m){
        if(!Set.of("type","operation","chunk_id","rev","split_at","source").containsAll(m.fieldNames()))throw new IllegalArgumentException("Invalid revision fields");
        String source=m.getString("source","human"); // WS commands default to human.
        JsonObject c=chunks.get(m.getString("chunk_id"));if(c==null)return;
        if(sourcePriority(c.getString("source",""))>sourcePriority(source)){warning("Ревизия отклонена арбитром: "+source+" ниже текущего "+c.getString("source"));return;}
        int rev=m.getInteger("rev");if(rev<=c.getInteger("rev"))return;
        if(rev!=c.getInteger("rev")+1)throw new IllegalArgumentException("Revision conflict; refresh state");
        if(System.currentTimeMillis()-c.getLong("updated_at")>180000){warning("Окно ревизии 3 минуты истекло");return;}
        String op=m.getString("operation");List<String> ids=new ArrayList<>(c.getJsonArray("sentence_ids").getList());
        JsonArray replaced=new JsonArray().add(c.getString("id")),updated=new JsonArray();
        switch(op){
            case "confirm" -> updated.add(chunk(ids,c.getString("id"),rev,"confirmed","confirm").put("source",source));
            case "split" -> {int at=m.getInteger("split_at",-1);if(at<1||at>=ids.size())throw new IllegalArgumentException("Invalid split index");updated.add(chunk(ids.subList(0,at),c.getString("id"),rev,"confirmed","split").put("source",source));updated.add(chunk(ids.subList(at,ids.size()),UUID.randomUUID().toString(),1,"confirmed","split").put("source",source));}
            case "merge" -> {var ordered=orderedChunks();int at=ordered.indexOf(c);if(at==ordered.size()-1)throw new IllegalArgumentException("Нет следующего куска");var next=ordered.get(at+1);if(System.currentTimeMillis()-next.getLong("updated_at")>180000)throw new IllegalArgumentException("Окно ревизии истекло");ids.addAll(next.getJsonArray("sentence_ids").getList());if(ids.stream().map(sentences::get).mapToInt(s->Text.words(s.getString("text"))).sum()>models.chunkSizeEmergency())throw new IllegalArgumentException("Слияние превысит лимит слов");replaced.add(next.getString("id"));updated.add(chunk(ids,c.getString("id"),rev,"confirmed","merge").put("source",source));}
            default -> throw new IllegalArgumentException("Unknown revision operation");
        }
        event("chunk_revise",new JsonObject().put("operation",op).put("source",source).put("replace_ids",replaced).put("chunks",updated));
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
    /** T-S11: depth-score dips inside a chunk become curator candidates. */
    List<Integer> depthCandidates(List<String> ids){
        List<Integer> out=new ArrayList<>();
        for(int i=1;i<ids.size();i++){
            float[] a=embeddings.get(ids.get(i-1)),b=embeddings.get(ids.get(i));
            if(a==null||b==null)continue;
            double cos=Text.cosine(a,b);
            if(emaBaseline-cos>Math.max(0.12,1.6*emaDispersion)&&cos<0.55)out.add(i);
        }
        return out;
    }
    /** T-S8: apply every verified boundary; iterate from the end so earlier indices stay valid. */
    void applyBoundaries(JsonObject anchor,List<Integer> boundaries){
        if(boundaries.isEmpty()){
            revise(new JsonObject().put("type","revise").put("operation","confirm").put("source","curator").put("chunk_id",anchor.getString("id")).put("rev",anchor.getInteger("rev")+1).put("split_at",0));
            return;
        }
        for(int bi=boundaries.size()-1;bi>=0;bi--){
            int at=boundaries.get(bi);
            List<String> curIds=new ArrayList<>(anchor.getJsonArray("sentence_ids").getList());
            if(at<1||at>=curIds.size())continue;
            revise(new JsonObject().put("type","revise").put("operation","split").put("source","curator").put("chunk_id",anchor.getString("id")).put("rev",anchor.getInteger("rev")+1).put("split_at",at));
            JsonObject left=chunks.get(anchor.getString("id"));
            if(left==null)break;
            anchor=left;
        }
    }
    void curate(){
        if(sketch||mode.equals("demo")||curating||generating)return;
        List<JsonObject> recent=orderedChunks().stream().filter(c->System.currentTimeMillis()-c.getLong("updated_at")<180000&&c.getString("status").equals("provisional")).toList();
        if(recent.isEmpty())return;
        JsonObject c=recent.getFirst();List<String> ids=c.getJsonArray("sentence_ids").getList();
        if(ids.size()<2||ids.size()>60)return; // T-S8: window widened from 25 to 60; size caps bound words.
        curating=true;List<String> texts=ids.stream().map(sentences::get).map(s->s.getString("text")).toList();
        List<Integer> candidates=depthCandidates(ids); // T-S11: curator verifies, does not discover
        Thread.startVirtualThread(()->{try{var verified=llm.verifyBoundaries(texts,candidates);submit(()->{try{JsonObject current=chunks.get(c.getString("id"));if(current!=null&&current.getInteger("rev").equals(c.getInteger("rev")))applyBoundaries(current,verified);}finally{curating=false;}});}catch(Exception e){submit(()->curating=false);}});
    }
    /** T-S6: phase-2 confirm pass with look-ahead. Runs every 5 s on the clock scheduler. */
    void confirmChunkPass(){
        if(stopped||mode.equals("demo"))return;
        var prov=orderedChunks().stream().filter(c->"provisional".equals(c.getString("status"))).toList();
        if(prov.isEmpty())return;
        JsonObject last=prov.get(prov.size()-1);
        if(System.currentTimeMillis()-last.getLong("updated_at")<models.confirmerDelayMs())return; // chunk still growing
        List<String> lastIds=new ArrayList<>(last.getJsonArray("sentence_ids").getList());
        // 1) merge with previous provisional when look-ahead agrees
        if(prov.size()>=2){
            JsonObject prev=prov.get(prov.size()-2);
            List<String> prevIds=prev.getJsonArray("sentence_ids").getList();
            float[] a=embeddings.get(prevIds.get(prevIds.size()-1));
            float[] b=embeddings.get(lastIds.get(0));
            long gap=last.getLong("t0")-prev.getLong("t1");
            if(a!=null&&b!=null&&gap>=0&&gap<2000&&Text.cosine(a,b)>models.coalesceThreshold()){
                revise(new JsonObject().put("type","revise").put("operation","merge").put("source","confirmer").put("chunk_id",prev.getString("id")).put("rev",prev.getInteger("rev")+1).put("split_at",0));
                return;
            }
        }
        // 2) split on an internal depth dip
        if(lastIds.size()>=6){
            int mid=lastIds.size()/2;
            float[] a=embeddings.get(lastIds.get(mid-1));
            float[] b=embeddings.get(lastIds.get(mid));
            if(a!=null&&b!=null){
                double cos=Text.cosine(a,b);
                if(emaBaseline-cos>Math.max(0.12,2*emaDispersion)&&cos<0.55){
                    revise(new JsonObject().put("type","revise").put("operation","split").put("source","confirmer").put("chunk_id",last.getString("id")).put("rev",last.getInteger("rev")+1).put("split_at",mid));
                    return;
                }
            }
        }
        // 3) confirm
        revise(new JsonObject().put("type","revise").put("operation","confirm").put("source","confirmer").put("chunk_id",last.getString("id")).put("rev",last.getInteger("rev")+1).put("split_at",0));
    }
    JsonObject metrics(){long[] sorted=latencies.stream().mapToLong(Long::longValue).sorted().toArray();return new JsonObject().put("type","metrics").put("current_ms",latencies.isEmpty()?0:latencies.getLast()).put("p95_ms",sorted.length==0?0:sorted[(int)Math.ceil(sorted.length*.95)-1]).put("chunks",chunks.size()).put("sentences",sentences.size()).put("audio_queue",audioWorker.getQueue().size()).put("mode",mode);}
    void snapshot(Consumer<JsonObject> cb){submit(()->cb.accept(new JsonObject().put("session_id",id).put("seq",seq).put("sentences",new JsonArray(new ArrayList<>(sentences.values()))).put("chunks",new JsonArray(orderedChunks())).put("slides",new JsonArray(new ArrayList<>(slides.values()))).put("metrics",metrics())));}
    public void close(){closed=true;clock.shutdownNow();state.shutdown();audioWorker.shutdown();inference.shutdown();if(socket!=null)socket.close();Thread.startVirtualThread(()->{try{audioWorker.awaitTermination(30,TimeUnit.SECONDS);if(audio!=null)audio.close();}catch(Exception ignored){}});}
}
