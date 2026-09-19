package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.JsonObject;
import java.util.*;

class ConfirmPassTest {
    static Session liveSession(String id,Store store)throws Exception{
        var s=new Session(id,"live",store,new Models(false),new Llm());
        s.clock.shutdownNow();s.generating=true;
        return s;
    }
    static String words(int n){StringBuilder b=new StringBuilder("W0");for(int i=1;i<n;i++)b.append(" w").append(i);return b.append(".").toString();} // capital first letter: Text.sentences() only splits before uppercase
    static JsonObject lastChunk(Session s){var l=s.orderedChunks();return l.get(l.size()-1);}

    @Test void stableProvisionalChunkGetsConfirmed()throws Exception{
        Store store=new Store();store.create("cp1","hash","live");
        try(var s=liveSession("cp1",store)){
            s.acceptFinal(words(30),0,2000);s.commit("test");
            var c=lastChunk(s);
            c.put("updated_at",System.currentTimeMillis()-5000);
            s.confirmChunkPass();
            assertEquals("confirmed",s.chunks.get(c.getString("id")).getString("status"));
            assertEquals("confirmer",s.chunks.get(c.getString("id")).getString("source"));
        }
    }

    @Test void recentlyUpdatedChunkIsSkipped()throws Exception{
        Store store=new Store();store.create("cp2","hash","live");
        try(var s=liveSession("cp2",store)){
            s.acceptFinal(words(30),0,2000);s.commit("test");
            s.confirmChunkPass(); // updated_at just refreshed → skip
            assertEquals("provisional",lastChunk(s).getString("status"));
        }
    }

    @Test void similarAdjacentProvisionalsMerge()throws Exception{
        Store store=new Store();store.create("cp3","hash","live");
        try(var s=liveSession("cp3",store)){
            s.acceptFinal(words(30),0,2000);s.commit("test");
            s.acceptFinal(words(30),2500,4500);s.commit("test"); // gap 0.5 s
            assertEquals(2,s.chunks.size());
            float[] v=SemanticDepthScoreTest.vec(7);
            for(var c:s.chunks.values()){
                List<String> ids=c.getJsonArray("sentence_ids").getList();
                for(String sid:ids)s.embeddings.put(sid,v);
                c.put("updated_at",System.currentTimeMillis()-5000);
            }
            s.confirmChunkPass();
            assertEquals(1,s.chunks.size());
            var merged=lastChunk(s);
            assertEquals("confirmed",merged.getString("status"));
            assertEquals("confirmer",merged.getString("source"));
        }
    }

    @Test void internalDipSplitsChunk()throws Exception{
        Store store=new Store();store.create("cp4","hash","live");
        try(var s=liveSession("cp4",store)){
            StringBuilder two=new StringBuilder();
            for(int i=0;i<3;i++)two.append(words(20)).append(' ');
            for(int i=0;i<3;i++)two.append(words(20)).append(' ');
            s.acceptFinal(two.toString(),0,6000);s.commit("test");
            var c=lastChunk(s);
            assertEquals(6,c.getJsonArray("sentence_ids").size());
            List<String> ids=c.getJsonArray("sentence_ids").getList();
            float[] a=SemanticDepthScoreTest.vec(1),b=SemanticDepthScoreTest.vec(2);
            for(int i=0;i<ids.size();i++)s.embeddings.put(ids.get(i),i<3?a:b);
            s.emaBaseline=0.95;s.emaDispersion=0.02;s.emaCount=20;
            c.put("updated_at",System.currentTimeMillis()-5000);
            s.confirmChunkPass();
            assertEquals(2,s.chunks.size());
            for(var x:s.chunks.values())assertEquals("confirmed",x.getString("status"));
        }
    }
}
