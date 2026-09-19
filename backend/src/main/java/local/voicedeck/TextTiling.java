package local.voicedeck;

import java.util.*;

/** Bilateral TextTiling-style pass over a whole session after stop.
 *  Scores each gap with a symmetric window of block embeddings, then keeps
 *  valleys whose prominence beats an adaptive threshold. */
public final class TextTiling {
    private TextTiling(){}

    /** Returns sentence indices (1..n-1) where a new topic starts. */
    public static List<Integer> boundaries(List<float[]> vectors,int window,double minDepth){
        int n=vectors.size();
        List<Integer> out=new ArrayList<>();
        if(n<2*window+2)return out;
        double[] gap=new double[n];
        for(int i=window;i<=n-window;i++){
            float[] left=mean(vectors.subList(i-window,i));
            float[] right=mean(vectors.subList(i,Math.min(n,i+window)));
            gap[i]=Text.cosine(left,right);
        }
        double[] depth=new double[n];
        for(int i=window+1;i<=n-window-1;i++)depth[i]=Math.max(0,gap[i-1]-gap[i])+Math.max(0,gap[i+1]-gap[i]);
        double mean=0;int cnt=0;
        for(int i=window+1;i<=n-window-1;i++){mean+=depth[i];cnt++;}
        if(cnt==0)return out;
        mean/=cnt;double var=0;
        for(int i=window+1;i<=n-window-1;i++){double d=depth[i]-mean;var+=d*d;}
        double thr=Math.max(minDepth,mean+Math.sqrt(var/cnt));
        for(int i=window+1;i<=n-window-1;i++)
            if(depth[i]>=thr&&(out.isEmpty()||i-out.get(out.size()-1)>=window))out.add(i);
        return out;
    }

    private static float[] mean(List<float[]> vs){
        int d=vs.get(0).length;float[] m=new float[d];
        for(float[] v:vs)for(int i=0;i<d;i++)m[i]+=v[i]/vs.size();
        double n=0;for(float x:m)n+=x*x;
        if(n>0)for(int i=0;i<d;i++)m[i]/=(float)Math.sqrt(n);
        return m;
    }
}
