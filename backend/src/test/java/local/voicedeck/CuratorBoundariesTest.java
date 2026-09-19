package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.*;
import java.util.*;

class CuratorBoundariesTest {
    static Session liveSession(String id,Store store)throws Exception{
        var s=new Session(id,"live",store,new Models(false),new Llm());
        s.clock.shutdownNow();s.generating=true;
        return s;
    }
    static void feedSentences(Session s,int count)throws Exception{
        StringBuilder text=new StringBuilder();
        for(int i=0;i<count;i++)text.append("Предложение номер ").append(i).append(" с достаточным числом слов внутри. ");
        s.acceptFinal(text.toString(),0,count*1000L);
        s.commit("test");
    }

    @Test void emptyBoundariesConfirmsChunk()throws Exception{
        Store store=new Store();store.create("cb0","hash","live");
        try(var s=liveSession("cb0",store)){
            feedSentences(s,4);
            var c=s.orderedChunks().get(0);
            s.applyBoundaries(c,List.of());
            assertEquals("confirmed",s.chunks.get(c.getString("id")).getString("status"));
            assertEquals("curator",s.chunks.get(c.getString("id")).getString("source"));
        }
    }

    @Test void threeBoundariesProduceThreeSplits()throws Exception{
        Store store=new Store();store.create("cb3","hash","live");
        try(var s=liveSession("cb3",store)){
            feedSentences(s,10);
            var c=s.orderedChunks().get(0);
            s.applyBoundaries(c,List.of(3,5,8));
            // [0,3) [3,5) [5,8) [8,10) — anchor splits from the end: 3 splits → 4 chunks.
            assertEquals(4,s.chunks.size());
            var sizes=s.orderedChunks().stream().map(x->x.getJsonArray("sentence_ids").size()).toList();
            assertEquals(List.of(3,2,3,2),sizes);
            for(var x:s.chunks.values())assertEquals("curator",x.getString("source"));
        }
    }

    @Test void outOfRangeBoundariesSkipped()throws Exception{
        Store store=new Store();store.create("cbX","hash","live");
        try(var s=liveSession("cbX",store)){
            feedSentences(s,6);
            var c=s.orderedChunks().get(0);
            s.applyBoundaries(c,List.of(0,6,99));
            assertEquals(1,s.chunks.size()); // nothing applied; anchor untouched
        }
    }

    @Test void depthCandidatesFromEmbeddings()throws Exception{
        Store store=new Store();store.create("dc","hash","live");
        try(var s=liveSession("dc",store)){
            feedSentences(s,6);
            var c=s.orderedChunks().get(0);
            List<String> ids=c.getJsonArray("sentence_ids").getList();
            // all identical except a hard dip between index 2 and 3
            float[] a=SemanticDepthScoreTest.vec(1),b=SemanticDepthScoreTest.vec(2);
            for(int i=0;i<ids.size();i++)s.embeddings.put(ids.get(i),i<3?a:b);
            // prime EMA on high-cosine region
            s.emaBaseline=0.9;s.emaDispersion=0.02;s.emaCount=10;
            List<Integer> cand=s.depthCandidates(ids);
            assertEquals(List.of(3),cand);
        }
    }

    @Test void verifyBoundariesFiltersToCandidateSubset()throws Exception{
        // Mock LLM endpoint returning a subset of candidates.
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/chat/completions",ex->{
            String content=new JsonObject().put("verified",new JsonArray().add(2)).encode();
            String body=new JsonObject().put("choices",new JsonArray().add(new JsonObject().put("message",new JsonObject().put("content",content)))).encode();
            byte[]b=body.getBytes();ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        try{
            int port=server.getAddress().getPort();
            var llm=new Llm("http://127.0.0.1:"+port);
            List<Integer> out=llm.verifyBoundaries(List.of("a.","b.","c.","d."),List.of(2,3));
            assertEquals(List.of(2),out);
            assertEquals(List.of(),llm.verifyBoundaries(List.of("a."),List.of()));
        }finally{server.stop(0);}
    }
}
