package local.voicedeck;

import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/** HTTP client for Ollama {@code /v1/embeddings} (OpenAI-compatible).
 *  Local network only; SSRF guard mirrors {@link Llm}.
 *  Returns L2-normalized vectors to keep {@link Text#cosine} compatible. */
public final class EmbeddingClient implements AutoCloseable {
    private final HttpClient http;
    private final String url;
    private final String model;
    private final int dimension;
    private final boolean enabled;

    public EmbeddingClient(){
        this(Main.env("EMBEDDING_URL","http://127.0.0.1:11434/v1"),
             Main.env("EMBEDDING_MODEL","bge-m3-embed"),
             Integer.parseInt(Main.env("EMBEDDING_DIMENSION","1024")),
             !Main.env("EMBEDDING_BACKEND","ollama").equals("disabled"),
             HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build());
    }

    public EmbeddingClient(String url,String model,int dimension,boolean enabled,HttpClient http){
        this.url=url;this.model=model;this.dimension=dimension;this.enabled=enabled;this.http=http;
        URI uri=URI.create(url);
        if(!"http".equals(uri.getScheme())&&!"https".equals(uri.getScheme()))throw new IllegalArgumentException("EMBEDDING_URL must use HTTP(S)");
        if(!enabled)return;
        try{for(InetAddress ip:InetAddress.getAllByName(uri.getHost()))if(!isLocalAddress(ip))throw new IllegalArgumentException("EMBEDDING_URL must resolve inside the local network");}
        catch(UnknownHostException e){throw new IllegalArgumentException("Cannot resolve embedding host",e);}
    }

    public float[] embed(String text)throws Exception{
        if(!enabled||text==null||text.isBlank())return null;
        var body=new JsonObject().put("model",model).put("input",new JsonArray().add(text));
        var req=HttpRequest.newBuilder(URI.create(url+"/embeddings")).timeout(Duration.ofSeconds(10)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body.encode())).build();
        var res=http.send(req,HttpResponse.BodyHandlers.ofString());
        if(res.statusCode()!=200)throw new IllegalStateException("Embedding HTTP "+res.statusCode());
        var arr=new JsonObject(res.body()).getJsonArray("data").getJsonObject(0).getJsonArray("embedding");
        if(arr.size()!=dimension)throw new IllegalStateException("Expected "+dimension+" dims, got "+arr.size());
        float[] v=new float[arr.size()];
        for(int i=0;i<v.length;i++)v[i]=arr.getFloat(i);
        double norm=0;for(float x:v)norm+=x*x;
        if(norm>0)for(int i=0;i<v.length;i++)v[i]/=(float)Math.sqrt(norm);
        return v;
    }

    /** Loopback / site-local / link-local / IPv6 ULA (fc00::/7). Docker Desktop resolves host.docker.internal to a ULA such as fdc4:f303:9324::254, which Java does not classify as site-local. */
    static boolean isLocalAddress(InetAddress ip){
        if(ip.isLoopbackAddress()||ip.isSiteLocalAddress()||ip.isLinkLocalAddress())return true;
        byte[] b=ip.getAddress();
        return b.length==16&&(b[0]&0xfe)==0xfc;
    }

    public boolean enabled(){return enabled;}
    public int dimension(){return dimension;}
    public String modelName(){return model;}
    public String url(){return url;}

    @Override public void close(){}
}
