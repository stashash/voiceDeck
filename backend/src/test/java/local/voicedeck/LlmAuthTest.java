package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.*;
import java.util.*;

/** Ключ VK и Project-ID уходят только на роутер VK; чужой адрес модели не пускается и ключа не получает. */
class LlmAuthTest {
    static final Map<String,String> VK=Map.of("VK_API_KEY","vk-secret","VK_PROJECT_ID","prj-1");

    @Test void vkRouterGetsKeyAndProject(){
        assertEquals(Map.of("Authorization","Bearer vk-secret","Project-ID","prj-1"),Llm.vkHeaders(Llm.VK_INFERENCE_URL,VK));
        new Llm(Llm.VK_INFERENCE_URL,VK);
    }

    @Test void otherAddressesGetNothing(){
        for(String url:List.of("https://evil.example/v1",
                "http://ai-demo.platformpreview.ru/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
                "https://ai-demo.platformpreview.ru:8443/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
                "https://ai-demo.platformpreview.ru/api/inference-providers-router/other-router/v1",
                "https://ai-demo.platformpreview.ru.evil.example/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
                "http://127.0.0.1:8000/v1"))
            assertEquals(Map.of(),Llm.vkHeaders(url,VK),url);
    }

    @Test void vkRouterWithoutKeyIsDisabledNotFatal(){
        // Чистый клон с .env.example без ключа: сервис стартует, модель просто не зовётся.
        var llm=new Llm(Llm.VK_INFERENCE_URL,Map.of());
        assertFalse(llm.enabled());
        assertThrows(IllegalStateException.class,()->llm.verifyBoundaries(List.of("a.","b.","c."),List.of(2)));
        assertTrue(new Llm(Llm.VK_INFERENCE_URL,VK).enabled());
    }

    @Test void requestCarriesHeadersToConfiguredRouter()throws Exception{
        var seen=new HashMap<String,String>();
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/v1/chat/completions",ex->{
            seen.put("auth",ex.getRequestHeaders().getFirst("Authorization"));
            seen.put("project",ex.getRequestHeaders().getFirst("Project-ID"));
            String content=new JsonObject().put("verified",new JsonArray().add(2)).encode();
            byte[]b=new JsonObject().put("choices",new JsonArray().add(new JsonObject().put("message",new JsonObject().put("content",content)))).encode().getBytes();
            ex.sendResponseHeaders(200,b.length);
            try(var os=ex.getResponseBody()){os.write(b);}
        });
        server.start();
        try{
            String base="http://127.0.0.1:"+server.getAddress().getPort()+"/v1";
            var env=new HashMap<>(VK);env.put("VK_INFERENCE_URL",base);
            assertEquals(List.of(2),new Llm(base,env).verifyBoundaries(List.of("a.","b.","c."),List.of(2)));
            assertEquals("Bearer vk-secret",seen.get("auth"));
            assertEquals("prj-1",seen.get("project"));
        }finally{server.stop(0);}
    }
}
