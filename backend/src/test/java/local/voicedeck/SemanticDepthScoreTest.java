package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;

class SemanticDepthScoreTest {
    static float[] vec(int seed){
        Random r=new Random(seed);float[] v=new float[1024];double n=0;
        for(int i=0;i<v.length;i++){v[i]=(float)r.nextGaussian();n+=v[i]*v[i];}
        n=Math.sqrt(n);for(int i=0;i<v.length;i++)v[i]/=n;return v;
    }
    static String sentenceOfWords(int n){
        StringBuilder b=new StringBuilder();
        for(int i=0;i<n;i++)b.append("слово").append(i).append(' ');
        return b.toString().trim()+".";
    }
    static void feed(Session s,int count,float[][] vectors)throws Exception{
        for(int i=0;i<count;i++)s.acceptFinal(sentenceOfWords(13),i*1000L,(i+1)*1000L);
        // Inject embeddings deterministically and run semantic() in order, as the inference callback would.
        List<String> ids=new ArrayList<>(s.pending);
        for(int i=0;i<ids.size();i++){s.embeddings.put(ids.get(i),vectors[Math.min(i,vectors.length-1)]);s.semantic(ids.get(i));}
    }

    @Test void monotoneSpeechProducesNoDriftCommits()throws Exception{
        Store store=new Store();store.create("mono","hash","live");
        try(var session=new Session("mono","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            float[] a=vec(1);
            feed(session,10,new float[][]{a});
            assertEquals(0,session.chunks.size());
        }
    }

    @Test void topicShiftProducesExactlyOneBoundary()throws Exception{
        Store store=new Store();store.create("shift","hash","live");
        try(var session=new Session("shift","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            float[] a=vec(1),b=vec(2);
            feed(session,10,new float[][]{a,a,a,a,a,b,b,b,b,b});
            assertEquals(1,session.chunks.size());
            assertEquals(5,session.orderedChunks().get(0).getJsonArray("sentence_ids").size());
            assertEquals(5,session.pending.size());
        }
    }

    @Test void alternatingTopicsGrowDispersionAndSuppressCommits()throws Exception{
        Store store=new Store();store.create("alt","hash","live");
        try(var session=new Session("alt","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            float[] a=vec(1),b=vec(2);
            feed(session,10,new float[][]{a,b,a,b,a,b,a,b,a,b});
            // Dispersion widens fast; threshold adapts. Allow at most one early commit before the guard kicks in.
            assertTrue(session.chunks.size()<=1,"expected <=1 chunk, got "+session.chunks.size());
        }
    }

    @Test void shortPendingNeverCommits()throws Exception{
        Store store=new Store();store.create("short","hash","live");
        try(var session=new Session("short","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            float[] a=vec(1),b=vec(2);
            // 3 sentences of 13 words = 39 < chunkSizeMin(60). No drift even with orthogonal shift.
            for(int i=0;i<3;i++)session.acceptFinal(sentenceOfWords(13),i*1000L,(i+1)*1000L);
            List<String> ids=new ArrayList<>(session.pending);
            for(int i=0;i<ids.size();i++){session.embeddings.put(ids.get(i),i<2?a:b);session.semantic(ids.get(i));}
            assertEquals(0,session.chunks.size());
        }
    }
}
