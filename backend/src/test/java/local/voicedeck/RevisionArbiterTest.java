package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.JsonObject;

class RevisionArbiterTest {
    static Session liveSession(String id,Store store)throws Exception{
        var s=new Session(id,"live",store,new Models(false),new Llm());
        s.clock.shutdownNow();s.generating=true;
        return s;
    }
    static JsonObject revise(String op,String source,String chunkId,int rev,int splitAt){
        var m=new JsonObject().put("type","revise").put("operation",op).put("chunk_id",chunkId).put("rev",rev).put("split_at",splitAt);
        if(source!=null)m.put("source",source);
        return m;
    }

    @Test void humanWinsOverConfirmer()throws Exception{
        Store store=new Store();store.create("ar1","hash","live");
        try(var s=liveSession("ar1",store)){
            s.acceptFinal("Первое предложение длинное наполнение словами для объёма. Второе предложение тоже достаточно длинное.",0,2000);
            s.commit("test");
            var c=s.orderedChunks().get(0);String id=c.getString("id");
            s.revise(revise("confirm",null,id,2,0)); // human (no source field)
            assertEquals("human",s.chunks.get(id).getString("source"));
            long seq=s.seq;
            s.revise(revise("split","confirmer",id,3,1)); // lower priority → rejected
            assertEquals(seq,s.seq);
            assertEquals(1,s.chunks.size());
        }
    }

    @Test void humanSplitAfterHumanConfirmWorks()throws Exception{
        Store store=new Store();store.create("ar2","hash","live");
        try(var s=liveSession("ar2",store)){
            s.acceptFinal("Первое предложение длинное наполнение словами для объёма. Второе предложение тоже достаточно длинное.",0,2000);
            s.commit("test");
            var c=s.orderedChunks().get(0);String id=c.getString("id");
            s.revise(revise("confirm",null,id,2,0));
            s.revise(revise("split",null,id,3,1));
            assertEquals(2,s.chunks.size());
        }
    }

    @Test void driftCoalesceOnFreshChunkAllowed()throws Exception{
        Store store=new Store();store.create("ar3","hash","live");
        try(var s=liveSession("ar3",store)){
            s.acceptFinal("Первая часть без точки в конце",0,1000);s.commit("test");
            s.acceptFinal("вторая часть продолжает мысль дальше.",1200,2400);s.commit("test");
            // coalesce ran in commitIds (live mode, continuation) — merged chunk carries source=drift.
            assertEquals(1,s.chunks.size());
            assertEquals("drift",s.orderedChunks().get(0).getString("source"));
        }
    }

    @Test void sourcePriorityOrder(){
        assertTrue(Session.sourcePriority("human")>Session.sourcePriority("offline"));
        assertTrue(Session.sourcePriority("offline")>Session.sourcePriority("curator"));
        assertTrue(Session.sourcePriority("curator")>Session.sourcePriority("confirmer"));
        assertTrue(Session.sourcePriority("confirmer")>Session.sourcePriority("drift"));
        assertEquals(0,Session.sourcePriority(null));
        assertEquals(0,Session.sourcePriority("unknown"));
    }
}
