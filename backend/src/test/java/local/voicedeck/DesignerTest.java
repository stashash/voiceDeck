package local.voicedeck;

import com.sun.net.httpserver.HttpServer;
import io.vertx.core.json.JsonObject;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.List;

class DesignerTest {
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
        assertThrows(IllegalArgumentException.class,()->new Designer("http://example.com",http));
    }

    @Test void rejectsNonHttp(){
        assertThrows(IllegalArgumentException.class,()->new Designer("ftp://127.0.0.1:8090",http));
    }

    @Test void blankUrlIsDisabled()throws Exception{
        var d=new Designer("",http);
        assertFalse(d.enabled());
        assertThrows(IllegalStateException.class,()->d.slide("ds","text",List.of()));
    }

    @Test void sendsExpectedBody()throws Exception{
        StringBuilder captured=new StringBuilder();
        server.createContext("/live/slide",ex->{
            captured.append(new String(ex.getRequestBody().readAllBytes(),StandardCharsets.UTF_8));
            ex.sendResponseHeaders(204,-1);ex.close();
        });
        server.start();
        var d=new Designer("http://127.0.0.1:"+port,http);
        assertNull(d.slide("ds1","Текст фрагмента",List.of("p1","p2")));
        var body=new JsonObject(captured.toString());
        assertEquals("ds1",body.getString("design_system_id"));
        assertEquals("Текст фрагмента",body.getString("chunk_text"));
        assertEquals(List.of("p1","p2"),body.getJsonArray("used_pattern_ids").getList());
    }

    @Test void parses200IntoTitleBulletsAndHtml()throws Exception{
        server.createContext("/live/slide",ex->{
            String scene="{\"slide_id\":\"s1\",\"pattern_id\":\"p7\",\"variant\":\"a\",\"theme\":\"light\",\"elements\":["
                +"{\"id\":\"e1\",\"type\":\"text\",\"role\":\"title\",\"box\":[0,0,1,1],\"text\":\"Заголовок слайда\"},"
                +"{\"id\":\"e2\",\"type\":\"text\",\"role\":\"body\",\"box\":[0,0,1,1],\"text\":\"Первый тезис\"},"
                +"{\"id\":\"e3\",\"type\":\"text\",\"role\":\"body\",\"box\":[0,0,1,1],\"text\":\"Второй тезис\"},"
                +"{\"id\":\"e4\",\"type\":\"icon\",\"role\":\"icon\",\"box\":[0,0,1,1]}]}";
            String body=new JsonObject().put("scene",new JsonObject(scene)).put("html","<section>слайд</section>").encode();
            byte[]b=body.getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type","application/json");
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        var d=new Designer("http://127.0.0.1:"+port,http);
        var result=d.slide("ds1","Текст",List.of());
        assertNotNull(result);
        assertEquals("Заголовок слайда",result.getString("title"));
        assertEquals(List.of("Первый тезис","Второй тезис"),result.getJsonArray("bullets").getList());
        assertEquals("",result.getString("notes"));
        assertEquals("p7",result.getString("pattern_id"));
        assertEquals("<section>слайд</section>",result.getString("html"));
    }

    @Test void status204MeansNoSlide()throws Exception{
        server.createContext("/live/slide",ex->{ex.sendResponseHeaders(204,-1);ex.close();});
        server.start();
        var d=new Designer("http://127.0.0.1:"+port,http);
        assertNull(d.slide("ds1","Текст",List.of()));
    }

    @Test void unexpectedStatusThrows(){
        server.createContext("/live/slide",ex->{ex.sendResponseHeaders(500,-1);ex.close();});
        server.start();
        var d=new Designer("http://127.0.0.1:"+port,http);
        assertThrows(IllegalStateException.class,()->d.slide("ds1","Текст",List.of()));
    }
}
