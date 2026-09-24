package local.voicedeck;

import com.sun.net.httpserver.HttpServer;
import io.vertx.core.json.JsonObject;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;

class DesignerSlideEventTest {
    static Session designerSession(String id,Store store,Designer designer)throws Exception{
        var s=new Session(id,"live",store,new Models(false),new Llm(),designer);
        s.clock.shutdownNow();s.designerMode=true;s.designSystemId="ds1";
        return s;
    }
    static void waitUntil(java.util.function.BooleanSupplier condition)throws InterruptedException{
        long deadline=System.currentTimeMillis()+5000;
        while(!condition.getAsBoolean()&&System.currentTimeMillis()<deadline)Thread.sleep(20);
    }

    @Test void slideEventCarriesHtmlAndPatternId()throws Exception{
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/live/slide",ex->{
            String scene="{\"slide_id\":\"s1\",\"pattern_id\":\"p1\",\"variant\":\"a\",\"theme\":\"light\",\"elements\":["
                +"{\"id\":\"e1\",\"type\":\"text\",\"role\":\"title\",\"box\":[0,0,1,1],\"text\":\"Заголовок\"},"
                +"{\"id\":\"e2\",\"type\":\"text\",\"role\":\"body\",\"box\":[0,0,1,1],\"text\":\"Тезис\"}]}";
            String body=new JsonObject().put("scene",new JsonObject(scene)).put("html","<section>слайд</section>").encode();
            byte[]b=body.getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type","application/json");
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        try{
            var designer=new Designer("http://127.0.0.1:"+server.getAddress().getPort(),HttpClient.newHttpClient());
            Store store=new Store();store.create("ds-ok","hash","live");
            try(var s=designerSession("ds-ok",store,designer)){
                s.acceptFinal("Фрагмент для дизайнера с достаточным числом слов внутри фразы.",0,3000);
                s.commit("test");
                String chunkId=s.orderedChunks().getFirst().getString("id");
                s.generate();
                waitUntil(()->s.slides.containsKey(chunkId));
                JsonObject slide=s.slides.get(chunkId);
                assertNotNull(slide);
                assertEquals("Заголовок",slide.getString("title"));
                assertEquals("Тезис",slide.getJsonArray("bullets").getString(0));
                assertEquals("p1",slide.getString("pattern_id"));
                assertEquals("<section>слайд</section>",slide.getString("html"));
                assertEquals("designer",slide.getString("source"));
            }
        }finally{server.stop(0);}
    }

    @Test void serviceFailureWarnsAndSessionKeepsAcceptingText()throws Exception{
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/live/slide",ex->{ex.sendResponseHeaders(500,-1);ex.close();});
        server.start();
        try{
            var designer=new Designer("http://127.0.0.1:"+server.getAddress().getPort(),HttpClient.newHttpClient());
            Store store=new Store();store.create("ds-fail","hash","live");
            try(var s=designerSession("ds-fail",store,designer)){
                s.acceptFinal("Фрагмент, который не получит слайд из-за сбоя сервиса дизайнера.",0,3000);
                s.commit("test");
                s.generate();
                waitUntil(()->!s.generating);
                assertTrue(s.retryAt>System.currentTimeMillis());
                assertTrue(s.slides.isEmpty());
                int before=s.sentences.size();
                s.acceptFinal("Ещё одна фраза после сбоя сервиса дизайнера.",3000,5000);
                assertTrue(s.sentences.size()>before);
            }
        }finally{server.stop(0);}
    }
}
