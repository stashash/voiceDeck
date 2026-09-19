package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.JsonObject;
import java.util.*;

class OfflinePassTest {
    static Session liveSession(String id,Store store)throws Exception{
        var s=new Session(id,"live",store,new Models(false),new Llm());
        s.clock.shutdownNow();s.generating=true;
        return s;
    }
    static void feed(Session s,int count)throws Exception{
        StringBuilder text=new StringBuilder();
        for(int i=0;i<count;i++)text.append("Предложение ").append(i).append(" с дюжиной слов для наполнения объёма текста блока. ");
        s.acceptFinal(text.toString(),0,count*1000L);
    }

    @Test void twoTopicBlocksBecomeTwoChunks()throws Exception{
        Store store=new Store();store.create("op1","hash","live");
        try(var s=liveSession("op1",store)){
            feed(s,12);
            float[] a=SemanticDepthScoreTest.vec(1),b=SemanticDepthScoreTest.vec(2);
            List<String> ids=new ArrayList<>(s.pending);
            for(int i=0;i<ids.size();i++)s.embeddings.put(ids.get(i),i<6?a:b);
            s.commit("flush");
            assertEquals(1,s.chunks.size());
            s.runOfflinePass();
            assertEquals(2,s.chunks.size());
            var sizes=s.orderedChunks().stream().map(c->c.getJsonArray("sentence_ids").size()).toList();
            assertEquals(List.of(6,6),sizes);
            for(var c:s.chunks.values())assertEquals("offline",c.getString("source"));
        }
    }

    @Test void uniformSpeechStaysOneChunk()throws Exception{
        Store store=new Store();store.create("op2","hash","live");
        try(var s=liveSession("op2",store)){
            feed(s,12);
            float[] a=SemanticDepthScoreTest.vec(1);
            for(String sid:new ArrayList<>(s.pending))s.embeddings.put(sid,a);
            s.commit("flush");
            s.runOfflinePass();
            assertEquals(1,s.chunks.size());
        }
    }

    @Test void humanEditsBlockOfflinePass()throws Exception{
        Store store=new Store();store.create("op3","hash","live");
        try(var s=liveSession("op3",store)){
            feed(s,12);
            float[] a=SemanticDepthScoreTest.vec(1),b=SemanticDepthScoreTest.vec(2);
            List<String> ids=new ArrayList<>(s.pending);
            for(int i=0;i<ids.size();i++)s.embeddings.put(ids.get(i),i<6?a:b);
            s.commit("flush");
            var c=s.orderedChunks().get(0);
            s.revise(new JsonObject().put("type","revise").put("operation","confirm").put("chunk_id",c.getString("id")).put("rev",2).put("split_at",0));
            long seq=s.seq;
            s.runOfflinePass();
            assertEquals(seq,s.seq); // no events emitted
            assertEquals(1,s.chunks.size());
            assertEquals("human",s.orderedChunks().get(0).getString("source"));
        }
    }

    @Test void sparseEmbeddingsSkipPass()throws Exception{
        Store store=new Store();store.create("op4","hash","live");
        try(var s=liveSession("op4",store)){
            feed(s,4); // < 6 with embeddings
            s.commit("flush");
            s.runOfflinePass();
            assertEquals(1,s.chunks.size());
        }
    }
}
