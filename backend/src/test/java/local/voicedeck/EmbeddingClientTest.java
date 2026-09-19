package local.voicedeck;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.util.concurrent.atomic.AtomicInteger;

class EmbeddingClientTest {
    private HttpServer server;
    private int port;
    private HttpClient http;

    @BeforeEach
    void start()throws Exception{
        server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        port=server.getAddress().getPort();
        http=HttpClient.newHttpClient();
    }

    @AfterEach
    void stop(){
        if(server!=null)server.stop(0);
    }

    @Test void rejectsNonLocalhost(){
        assertThrows(IllegalArgumentException.class,()->new EmbeddingClient("http://example.com/v1","x",1024,true,http));
    }

    @Test void rejectsNonHttp(){
        assertThrows(IllegalArgumentException.class,()->new EmbeddingClient("ftp://127.0.0.1:11434/v1","x",1024,true,http));
    }

    @Test void disabledSkipsGuardAndRequest()throws Exception{
        var c=new EmbeddingClient("http://example.com/v1","x",1024,false,http);
        assertFalse(c.enabled());
        assertNull(c.embed("hello"));
    }

    @Test void blankTextReturnsNull()throws Exception{
        server.createContext("/v1/embeddings",ex->{ex.sendResponseHeaders(200,-1);ex.close();});
        server.start();
        var c=new EmbeddingClient("http://127.0.0.1:"+port+"/v1","x",1024,true,http);
        assertNull(c.embed(""));
        assertNull(c.embed(null));
        assertNull(c.embed("   "));
    }

    @Test void embedsAndNormalizes()throws Exception{
        AtomicInteger calls=new AtomicInteger();
        server.createContext("/v1/embeddings",ex->{
            calls.incrementAndGet();
            String body="{\"data\":[{\"embedding\":[3.0,4.0]}]}";
            byte[]b=body.getBytes();
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        var c=new EmbeddingClient("http://127.0.0.1:"+port+"/v1","bge-m3-embed",2,true,http);
        float[] v=c.embed("hello");
        assertNotNull(v);
        assertEquals(2,v.length);
        assertEquals(1,calls.get());
        // 3/5=0.6, 4/5=0.8 — L2-normalized.
        assertEquals(0.6f,v[0],1e-5);
        assertEquals(0.8f,v[1],1e-5);
        assertEquals("bge-m3-embed",c.modelName());
        assertEquals(2,c.dimension());
        assertTrue(c.enabled());
    }

    @Test void rejectsDimensionMismatch(){
        server.createContext("/v1/embeddings",ex->{
            String body="{\"data\":[{\"embedding\":[0.1,0.2,0.3]}]}";
            byte[]b=body.getBytes();
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        var c=new EmbeddingClient("http://127.0.0.1:"+port+"/v1","x",10,true,http);
        assertThrows(IllegalStateException.class,()->c.embed("hello"));
    }

    @Test void httpErrorThrows(){
        server.createContext("/v1/embeddings",ex->{ex.sendResponseHeaders(503,-1);ex.close();});
        server.start();
        var c=new EmbeddingClient("http://127.0.0.1:"+port+"/v1","x",2,true,http);
        assertThrows(IllegalStateException.class,()->c.embed("hello"));
    }

    @Test void alreadyNormalizedVectorStaysUnit()throws Exception{
        server.createContext("/v1/embeddings",ex->{
            // 0.6^2 + 0.8^2 = 1.0 — already normalized.
            String body="{\"data\":[{\"embedding\":[0.6,0.8]}]}";
            byte[]b=body.getBytes();
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        var c=new EmbeddingClient("http://127.0.0.1:"+port+"/v1","x",2,true,http);
        float[] v=c.embed("x");
        assertEquals(0.6f,v[0],1e-5);
        assertEquals(0.8f,v[1],1e-5);
    }

    @Test void ipv6UlaAcceptedAsLocal()throws Exception{
        // Docker Desktop resolves host.docker.internal to a ULA like fdc4:f303:9324::254.
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("fdc4:f303:9324::254")));
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("fc00::1")));
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("fd12:3456::1")));
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("127.0.0.1")));
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("192.168.1.10")));
        assertTrue(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("169.254.0.1")));
        assertFalse(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("8.8.8.8")));
        assertFalse(EmbeddingClient.isLocalAddress(java.net.InetAddress.getByName("2001:4860:4860::8888"))); // public IPv6
    }
}
