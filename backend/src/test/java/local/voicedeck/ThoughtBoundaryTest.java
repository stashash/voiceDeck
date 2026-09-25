package local.voicedeck;

import com.sun.net.httpserver.HttpServer;
import io.vertx.core.json.JsonObject;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

/** Live в режиме designer: фрагмент = законченная мысль. Пауза посреди мысли его не закрывает, новую тему видит модель. */
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
    /** Докладчик молчит pauseMs после последнего предложения; tick и ответ модели. */
    static void silence(Session s,long pauseMs)throws Exception{
        long end=s.sentences.get(s.pending.getLast()).getLong("t1");
        s.epoch=System.currentTimeMillis()-end-pauseMs;s.lastFinalWall=System.currentTimeMillis()-pauseMs;
        for(int i=0;i<20;i++){s.state.submit(s::tick).get();DesignerSlideEventTest.waitUntil(()->!s.askingBoundary);}
    }

    @Test void pauseInsideThoughtDoesNotCloseIt()throws Exception{
        try(var s=session("thought-pause")){
            s.acceptFinal("Начну с проблемы.",0,1500);silence(s,1800);
            s.acceptFinal("В прошлом году первая линия обрабатывала около сорока тысяч обращений в месяц.",3300,8000);silence(s,1800);
            s.acceptFinal("Каждое обращение стоило нам примерно сто двадцать рублей.",9800,13000);silence(s,1800);
            s.acceptFinal("Большая часть вопросов повторялась.",14800,17000);silence(s,1800);
            assertTrue(s.chunks.isEmpty(),"пауза 1,8 с посреди мысли не режет речь");
            assertTrue(questions.get()>0,"модель спрошена о границе");
        }
    }
    @Test void newTopicClosesPreviousThought()throws Exception{
        try(var s=session("thought-topic")){
            s.acceptFinal("Начну с проблемы.",0,1500);
            s.acceptFinal("В прошлом году первая линия обрабатывала около сорока тысяч обращений в месяц.",1800,6000);
            s.acceptFinal("Каждое обращение стоило нам примерно сто двадцать рублей.",6300,9000);
            s.acceptFinal("Теперь о результатах пилота.",11000,12500);silence(s,500);
            assertEquals(1,s.chunks.size());
            JsonObject c=s.orderedChunks().getFirst();
            assertEquals("thought",c.getString("reason"));
            assertEquals(3,c.getJsonArray("sentence_ids").size());
            assertEquals(1,s.pending.size(),"новая тема копится дальше");
        }
    }
    @Test void longSilenceClosesThought()throws Exception{
        try(var s=session("thought-silence")){
            s.acceptFinal("Спасибо, готов ответить на вопросы.",0,2000);silence(s,4500);
            assertEquals(1,s.chunks.size());
            assertEquals("pause",s.orderedChunks().getFirst().getString("reason"));
        }
    }
    @Test void longSentenceInProgressIsNotSilence()throws Exception{
        try(var s=session("thought-speaking")){
            s.acceptFinal("Начну с проблемы.",0,1500);
            // Следующее предложение звучит уже 5 с: финала нет, но распознавание шлёт промежуточный текст.
            s.lastFinalWall=System.currentTimeMillis()-5000;s.lastSpeechWall=System.currentTimeMillis()-300;
            s.state.submit(s::tick).get();
            assertTrue(s.chunks.isEmpty(),"пока человек говорит, мысль не закрывается");
        }
    }
    @Test void confirmKeepsSlide()throws Exception{
        try(var s=session("thought-confirm")){
            s.acceptFinal("Спасибо, готов ответить на вопросы.",0,2000);s.commit("test");
            JsonObject c=s.orderedChunks().getFirst();String id=c.getString("id");
            s.event("slide",new JsonObject().put("slide",new JsonObject().put("chunk_id",id).put("rev",1).put("title","Вопросы").put("bullets",new io.vertx.core.json.JsonArray()).put("notes","").put("html","<section>слайд</section>")));
            s.revise(new JsonObject().put("type","revise").put("operation","confirm").put("source","confirmer").put("chunk_id",id).put("rev",2).put("split_at",0));
            assertEquals(2,s.slides.get(id).getInteger("rev"),"подтверждённый фрагмент держит свой слайд");
            assertEquals("<section>слайд</section>",s.slides.get(id).getString("html"));
        }
    }
    @Test void everyClosedThoughtIsConfirmed()throws Exception{
        try(var s=session("thought-confirm-all")){
            s.acceptFinal("Отдельно стоит сказать про безопасность.",0,2000);s.commit("thought");
            s.acceptFinal("В следующем году мы добавим электровелосипеды.",4000,6000);s.commit("pause");
            String first=s.orderedChunks().getFirst().getString("id");
            s.event("slide",new JsonObject().put("slide",new JsonObject().put("chunk_id",first).put("rev",1).put("title","Безопасность").put("bullets",new io.vertx.core.json.JsonArray()).put("notes","").put("html","<section>1</section>")));
            s.confirmChunkPass();
            assertEquals("confirmed",s.chunks.get(first).getString("status"),"мысль со слайдом подтверждается, хотя она не последняя");
            assertEquals("provisional",s.orderedChunks().getLast().getString("status"),"без слайда ждёт задержку");
        }
    }
    @Test void designerDownFallsBackToPauses()throws Exception{
        server.removeContext("/live/boundary");
        server.createContext("/live/boundary",ex->{ex.sendResponseHeaders(500,-1);ex.close();});
        try(var s=session("thought-down")){
            s.acceptFinal("Начну с проблемы, которая мешала всей команде поддержки весь прошлый год подряд и отнимала у операторов по три часа каждый рабочий день.",0,4000);
            s.acceptFinal("Каждое обращение стоило нам примерно сто двадцать рублей и час работы.",4300,8000);silence(s,1500);
            assertEquals(1,s.chunks.size(),"без ответа модели фрагмент закрывает пауза, как раньше");
        }
    }
}
