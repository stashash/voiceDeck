package local.voicedeck;

import com.sun.net.httpserver.HttpServer;
import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

/** Live в режиме designer: фрагмент закрывается на паузе и сразу даёт слайд; продолжает ли он мысль предыдущего,
 *  решает модель. Продолжает — фрагменты склеиваются, новая мысль — прежний фрагмент подтверждается и уходит в зал. */
class ThoughtBoundaryTest {
    HttpServer server;
    final AtomicInteger questions=new AtomicInteger();

    @BeforeEach void start()throws Exception{
        server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        // Модель-подделка: новая мысль начинается со слова «Теперь».
        server.createContext("/live/boundary",ex->{
            questions.incrementAndGet();
            var body=new JsonObject(new String(ex.getRequestBody().readAllBytes(),StandardCharsets.UTF_8));
            byte[] out=new JsonObject().put("new_thought",body.getString("next_sentence").startsWith("Теперь")).encode().getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type","application/json");
            ex.sendResponseHeaders(200,out.length);
            try(var os=ex.getResponseBody()){os.write(out);}
        });
        server.createContext("/live/slide",ex->{ex.sendResponseHeaders(204,-1);ex.close();});
        server.start();
    }
    @AfterEach void stop(){server.stop(0);}

    Session session(String id)throws Exception{
        var designer=new Designer("http://127.0.0.1:"+server.getAddress().getPort(),HttpClient.newHttpClient());
        Store store=new Store();store.create(id,"hash","live");
        var s=DesignerSlideEventTest.designerSession(id,store,designer);
        s.generating=true; // слайды в этом тесте не нужны
        return s;
    }
    /** Пауза после фразы: tick закрывает фрагмент, модель отвечает про пару фрагментов. */
    static void pause(Session s)throws Exception{
        s.lastFinalWall=System.currentTimeMillis()-1500;
        for(int i=0;i<10;i++){s.state.submit(s::tick).get();DesignerSlideEventTest.waitUntil(()->!s.judging);}
    }

    @Test void pauseClosesFragmentAtOnce()throws Exception{
        try(var s=session("live-fast")){
            s.acceptFinal("Начну с проблемы.",0,1500);pause(s);
            assertEquals(1,s.chunks.size(),"слайд из речи начинается на первой паузе, а не в конце мысли");
        }
    }
    @Test void continuationMergesIntoOneSlide()throws Exception{
        try(var s=session("live-merge")){
            s.acceptFinal("Начну с проблемы.",0,1500);pause(s);
            String first=s.orderedChunks().getFirst().getString("id");
            s.acceptFinal("Обращений в прошлом году было сорок тысяч.",3000,6000);pause(s);
            assertEquals(1,s.chunks.size(),"продолжение мысли склеивается с ней");
            JsonObject c=s.chunks.get(first);
            assertEquals(2,c.getJsonArray("sentence_ids").size());
            assertEquals("provisional",c.getString("status"),"мысль ещё может расти");
            assertTrue(questions.get()>0);
        }
    }
    @Test void newThoughtSendsPreviousToHall()throws Exception{
        try(var s=session("live-new")){
            s.acceptFinal("Начну с проблемы.",0,1500);pause(s);
            s.acceptFinal("Теперь о результатах пилота.",3000,5000);pause(s);
            assertEquals(2,s.chunks.size());
            assertEquals("confirmed",s.orderedChunks().getFirst().getString("status"),"прежняя мысль закончена и уходит в зал");
            assertEquals("provisional",s.orderedChunks().getLast().getString("status"));
        }
    }
    @Test void confirmKeepsSlide()throws Exception{
        try(var s=session("live-confirm")){
            s.acceptFinal("Спасибо, готов ответить на вопросы.",0,2000);s.commit("test");
            JsonObject c=s.orderedChunks().getFirst();String id=c.getString("id");
            s.event("slide",new JsonObject().put("slide",new JsonObject().put("chunk_id",id).put("rev",1).put("title","Вопросы").put("bullets",new JsonArray()).put("notes","").put("html","<section>слайд</section>")));
            s.revise(new JsonObject().put("type","revise").put("operation","confirm").put("source","confirmer").put("chunk_id",id).put("rev",2).put("split_at",0));
            assertEquals(2,s.slides.get(id).getInteger("rev"),"подтверждённый фрагмент держит свой слайд");
            assertEquals("<section>слайд</section>",s.slides.get(id).getString("html"));
        }
    }
    @Test void earlyAnswerSettlesFragmentAtOnce()throws Exception{
        try(var s=session("live-early")){
            s.acceptFinal("Начну с проблемы.",0,1500);pause(s);
            int before=questions.get();
            s.state.submit(()->s.askEarly("Теперь о результатах пилота",3000)).get();
            DesignerSlideEventTest.waitUntil(()->!s.judging);
            assertEquals(before+1,questions.get(),"вопрос задан, пока фраза ещё звучит");
            s.acceptFinal("Теперь о результатах пилота.",3000,5000);pause(s);
            assertEquals(before+1,questions.get(),"к закрытию фрагмента ответ уже есть, второй раз модель не спрашивают");
            assertEquals("confirmed",s.orderedChunks().getFirst().getString("status"),"прежняя мысль ушла в зал");
            assertEquals(2,s.chunks.size());
        }
    }
    @Test void freshThoughtGetsModelSlideFirst()throws Exception{
        try(var s=session("live-order")){
            s.acceptFinal("Начну с проблемы.",0,1500);s.commit("test");
            s.acceptFinal("Теперь о результатах пилота.",3000,5000);s.commit("test");
            var ordered=s.orderedChunks();String old=ordered.getFirst().getString("id"),fresh=ordered.getLast().getString("id");
            s.event("slide",new JsonObject().put("slide",new JsonObject().put("chunk_id",old).put("rev",1).put("title","Черновик").put("bullets",new JsonArray()).put("notes","").put("source","draft")));
            assertEquals(fresh,s.nextForSlide().getString("id"),"зал смотрит на то, что говорится сейчас");
            s.inFlight.add(fresh);
            assertEquals(old,s.nextForSlide().getString("id"),"прежняя мысль получает слайд следом");
        }
    }
    @Test void designerDownKeepsFragmentsFlowing()throws Exception{
        server.removeContext("/live/boundary");
        server.createContext("/live/boundary",ex->{ex.sendResponseHeaders(500,-1);ex.close();});
        try(var s=session("live-down")){
            s.acceptFinal("Начну с проблемы.",0,1500);pause(s);
            s.acceptFinal("Обращений в прошлом году было сорок тысяч.",3000,6000);pause(s);
            assertTrue(s.pending.isEmpty(),"без ответа модели речь всё равно режется на паузах");
            assertTrue(s.boundaryDownUntil>System.currentTimeMillis(),"склейка временно идёт по эмбеддингам");
        }
    }
}
