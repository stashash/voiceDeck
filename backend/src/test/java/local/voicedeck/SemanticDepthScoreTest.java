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
    /** Unit vector with cosine ≈ {@code cosine} to {@code base}: random component orthogonalized against base (Gram–Schmidt). */
    static float[] withCos(float[] base,double cosine,int seed){
        Random r=new Random(seed);float[] v=new float[base.length];double dot=0;
        for(int i=0;i<v.length;i++){v[i]=(float)r.nextGaussian();dot+=v[i]*base[i];}
        for(int i=0;i<v.length;i++)v[i]-=(float)dot*base[i];
        double n=0;for(float x:v)n+=x*x;n=Math.sqrt(n);
        double orth=Math.sqrt(Math.max(0,1-cosine*cosine));
        for(int i=0;i<v.length;i++)v[i]=(float)(v[i]/n*orth+base[i]*cosine);
        return v;
    }
    static String sentenceOfWords(int n){
        StringBuilder b=new StringBuilder();
        for(int i=0;i<n;i++)b.append("слово").append(i).append(' ');
        return b.toString().trim()+".";
    }
    /** Capitalized variant: Text.sentences() only splits before an uppercase letter, so multi-sentence paragraphs need it. */
    static String capitalSentenceOfWords(int n){
        StringBuilder b=new StringBuilder("Слово0");
        for(int i=1;i<n;i++)b.append(" слово").append(i);
        return b.append('.').toString();
    }
    static String paragraphOfSentences(int sentences,int words){
        StringBuilder b=new StringBuilder();
        for(int i=0;i<sentences;i++)b.append(capitalSentenceOfWords(words)).append(' ');
        return b.toString().trim();
    }
    static Session live(String id)throws Exception{
        Store store=new Store();store.create(id,"hash","live");
        var s=new Session(id,"live",store,new Models(false),new Llm());
        s.clock.shutdownNow();s.generating=true;
        return s;
    }
    static void feed(Session s,int count,int words,float[]... vectors)throws Exception{
        int base=s.streamIds.size();
        for(int i=0;i<count;i++)s.acceptFinal(sentenceOfWords(words),(base+i)*1000L,(base+i+1)*1000L);
        embedAndDetect(s,new ArrayList<>(s.streamIds.subList(base,s.streamIds.size())),vectors);
    }
    /** Inject embeddings positionally and run the stream detector, as the inference callback would. */
    static void embedAndDetect(Session s,List<String> ids,float[]... vectors){
        for(int i=0;i<ids.size();i++){s.embeddings.put(ids.get(i),vectors[Math.min(i,vectors.length-1)]);s.detectBoundary(ids.get(i));}
    }

    @Test void monotoneSpeechProducesNoDriftCommits()throws Exception{
        try(var session=live("mono")){
            float[] a=vec(1);
            feed(session,10,13,a);
            assertEquals(0,session.chunks.size());
        }
    }

    @Test void topicShiftProducesExactlyOneBoundary()throws Exception{
        try(var session=live("shift")){
            float[] a=vec(1),b=vec(2);
            feed(session,10,13,a,a,a,a,a,b,b,b,b,b);
            assertEquals(1,session.chunks.size());
            assertEquals(5,session.orderedChunks().get(0).getJsonArray("sentence_ids").size());
            assertEquals(5,session.pending.size());
            // Orthogonal shift (cos≈0 < emergencyThreshold 0.2) commits immediately as drift-emergency.
            assertEquals("drift-emergency",session.orderedChunks().get(0).getString("reason"));
        }
    }

    @Test void alternatingTopicsGrowDispersionAndSuppressCommits()throws Exception{
        try(var session=live("alt")){
            float[] a=vec(1),b=vec(2);
            feed(session,10,13,a,b,a,b,a,b,a,b,a,b);
            // Emergency dips accumulate ≥60 words once; allow at most one early commit before the guard kicks in.
            assertTrue(session.chunks.size()<=1,"expected <=1 chunk, got "+session.chunks.size());
        }
    }

    @Test void shortPendingNeverCommits()throws Exception{
        try(var session=live("short")){
            float[] a=vec(1),b=vec(2);
            // 3 sentences of 13 words = 39 < chunkSizeMin(60). No drift even with orthogonal shift.
            feed(session,3,13,a,a,b);
            assertEquals(0,session.chunks.size());
        }
    }

    @Test void shallowOutlierWithRecoveryIsRejectedByDepthFloor()throws Exception{
        try(var session=live("outlier")){
            float[] a=vec(1);
            feed(session,8,13,a,a,a,a,a,a,withCos(a,0.9,7),a);
            // Single dip to cos 0.9: depth ≈0.1 < depthFloor 0.12 → never a candidate, recovery changes nothing.
            assertEquals(0,session.chunks.size());
            assertNull(session.candidateSid);
        }
    }

    @Test void deepDipWithRecoveryConfirmsValleyAndCommits()throws Exception{
        try(var session=live("valley")){
            float[] a=vec(1),x=withCos(a,0.6,3),y=withCos(x,0.95,4),z=withCos(x,0.95,5);
            feed(session,9,20,a,a,a,a,a,a,x,y,z);
            // Dip to 0.6 (above emergency 0.2) becomes a candidate; the next pair recovers (0.95) → valley confirmed.
            assertEquals(1,session.chunks.size());
            assertEquals(6,session.orderedChunks().get(0).getJsonArray("sentence_ids").size());
            assertEquals("drift",session.orderedChunks().get(0).getString("reason"));
            assertEquals(3,session.pending.size());
        }
    }

    @Test void deeperDipMovesCandidate()throws Exception{
        try(var session=live("move")){
            float[] a=vec(1),x=withCos(a,0.6,3),deeper=withCos(a,0.45,6);
            feed(session,8,20,a,a,a,a,a,a,x,deeper);
            // The second dip (≈0.27 > emergency 0.2, depth greater) supersedes the first candidate; nothing committed yet.
            List<String> ids=new ArrayList<>(session.streamIds);
            assertEquals(ids.get(7),session.candidateSid);
            assertEquals(0,session.chunks.size());
        }
    }

    @Test void threeFlatSentencesApplyCandidateAtOriginalIndex()throws Exception{
        try(var session=live("flat")){
            float[] a=vec(1),x=withCos(a,0.6,3),u1=withCos(x,0.6,7),u2=withCos(u1,0.6,8),u3=withCos(u2,0.6,9);
            feed(session,10,20,a,a,a,a,a,a,x,u1,u2,u3);
            // Candidate at s7; three following pairs stay flat at cos≈0.6 (no recovery, no deepening) → apply at s7.
            assertEquals(1,session.chunks.size());
            assertEquals(6,session.orderedChunks().get(0).getJsonArray("sentence_ids").size());
        }
    }

    @Test void dipInsideProvisionalChunkSplitsViaChunkRevise()throws Exception{
        try(var session=live("insplit")){
            float[] a=vec(1),x=withCos(a,0.6,3);
            session.acceptFinal(paragraphOfSentences(10,20),0,10000);
            session.commit("test"); // one provisional chunk of 10 sentences
            assertEquals(1,session.chunks.size());
            assertEquals(10,session.orderedChunks().get(0).getJsonArray("sentence_ids").size());
            feed(session,0,0);
            embedAndDetect(session,new ArrayList<>(session.streamIds),a,a,a,a,a,a,x,x,x,x);
            // Dip at s7 is inside the committed provisional chunk → split via revise machinery, source "drift".
            assertEquals(2,session.chunks.size());
            var sizes=session.orderedChunks().stream().map(c->c.getJsonArray("sentence_ids").size()).toList();
            assertEquals(List.of(6,4),sizes);
            for(var c:session.chunks.values())assertEquals("drift",c.getString("source"));
            var reviseEvent=session.store.events("insplit",0).stream().filter(e->e.getString("type").equals("chunk_revise")).findFirst().orElseThrow();
            assertEquals("split",reviseEvent.getString("operation"));
            assertEquals("drift",reviseEvent.getString("source"));
        }
    }

    @Test void splitRejectedWhenHalfBelowMarkerMinWords()throws Exception{
        try(var session=live("smallhalf")){
            float[] a=vec(1),x=withCos(a,0.6,3),u=withCos(x,0.65,7);
            feed(session,8,20,a,a,a,a,a,a,a,x); // warm-up + dip at s8 → candidate, no immediate cut
            session.commit("test"); // provisional chunk [s1..s8]; candidate s8 stays remembered
            feed(session,1,20,u); // recovery at s9 confirms the valley → apply at s8
            // Right half inside the committed chunk would be 1 sentence (20 < markerMinWords 30) → split rejected.
            assertEquals(1,session.chunks.size());
            assertNull(session.candidateSid);
        }
    }

    @Test void bilateralGapHelperSeparatesTopics(){
        float[] a=vec(1),b=vec(2);
        java.util.List<float[]> vecs=java.util.List.of(a,a,a,a,a,b,b,b,b,b);
        // At at=5 (between a's and b's): left=mean(a,a), right=mean(b,b). cosine~0, gap~1.
        double gapBoundary=Text.bilateralGap(vecs,5,2);
        assertTrue(gapBoundary>0.5,"boundary gap should be large: "+gapBoundary);
        // At at=2 (within a's): left=mean(a,a), right=mean(a,a). cosine~1, gap~0.
        double gapWithin=Text.bilateralGap(vecs,2,2);
        assertTrue(gapWithin<0.05,"within-topic gap should be small: "+gapWithin);
        // At at=8 (within b's): also small.
        double gapWithinB=Text.bilateralGap(vecs,8,2);
        assertTrue(gapWithinB<0.05,"within-topic gap (b) should be small: "+gapWithinB);
    }

    @Test void depthIsComputedBeforeEmaUpdate()throws Exception{
        try(var session=live("order")){
            session.emaBaseline=0.9;session.emaDispersion=0.11875;session.emaCount=10;
            float[] a=vec(1),b=withCos(a,0.7,2);
            feed(session,2,20,a,b);
            // depth_before = 0.9−0.7 = 0.20 > max(0.12, 1.6·0.11875=0.19) → candidate.
            // depth_after would be 0.88−0.7 = 0.18 < 0.19 → no candidate. candidateSid proves the order.
            List<String> ids=new ArrayList<>(session.streamIds);
            assertEquals(ids.get(1),session.candidateSid);
            assertEquals(0.88,session.emaBaseline,1e-6);
            assertEquals(0,session.chunks.size());
        }
    }
}
