package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class DiscourseMarkersTest {
    @Test void markersAtSentenceStart(){
        assertTrue(Text.startsWithMarker("Итак, переходим к следующей теме."));
        assertTrue(Text.startsWithMarker("Теперь обсудим архитектуру решения."));
        assertTrue(Text.startsWithMarker("Далее рассмотрим вопрос производительности."));
        assertTrue(Text.startsWithMarker("Следующий пункт нашей программы."));
        assertTrue(Text.startsWithMarker("Перейдём к практической части."));
        assertTrue(Text.startsWithMarker("Наконец, подведём итоги."));
    }

    @Test void markerInsideSentenceDoesNotTrigger(){
        assertFalse(Text.startsWithMarker("Он сказал итак мы пошли дальше."));
        assertFalse(Text.startsWithMarker("Мы говорили, итак, о размерах."));
    }

    @Test void tooShortOrNullDoesNotTrigger(){
        assertFalse(Text.startsWithMarker(null));
        assertFalse(Text.startsWithMarker(""));
        assertFalse(Text.startsWithMarker("И."));
        assertFalse(Text.startsWithMarker("итак"));
    }

    @Test void ordinarySentencesDoNotTrigger(){
        assertFalse(Text.startsWithMarker("Сегодня мы обсудим, как превратить устный доклад в презентацию."));
        assertFalse(Text.startsWithMarker("Аудио обрабатывается на локальном компьютере."));
    }

    @Test void markerSentenceCommitsPendingBeforeItself()throws Exception{
        Store store=new Store();store.create("mk","hash","live");
        try(var session=new Session("mk","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            StringBuilder big=new StringBuilder();
            for(int i=0;i<5;i++)big.append("Предложение с достаточным количеством слов для наполнения объёма номер ").append(i).append(" продолжается дальше. ");
            session.acceptFinal(big.toString(),0,5000);
            assertTrue(session.chunks.isEmpty());
            session.acceptFinal("Итак, переходим к следующей теме.",5000,6000);
            assertEquals(1,session.chunks.size());
            var c=session.orderedChunks().get(0);
            assertFalse(c.getString("text").contains("Итак"));
            assertEquals(1,session.pending.size());
            assertEquals("marker",session.store.events("mk",0).stream().filter(e->e.getString("type").equals("chunk")).map(e->e.getString("reason")).findFirst().orElse(""));
        }
    }

    @Test void markerWithShortPendingDoesNotCommit()throws Exception{
        Store store=new Store();store.create("mk2","hash","live");
        try(var session=new Session("mk2","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            session.acceptFinal("Короткая реплика.",0,1000); // 2 words < 60
            session.acceptFinal("Итак, ещё одна тема.",1000,2000);
            assertTrue(session.chunks.isEmpty());
            assertEquals(2,session.pending.size());
        }
    }
}
