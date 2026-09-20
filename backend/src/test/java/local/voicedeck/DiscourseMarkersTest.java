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

    @Test void markerCommitsAtThirtyWordsNotBelow()throws Exception{
        Store store=new Store();store.create("mk3","hash","live");
        try(var session=new Session("mk3","live",store,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            // 2 sentences × 10 words = 20 words < markerMinWords(30): marker must NOT commit.
            session.acceptFinal("Одна короткая фраза с фиксированным количеством слов здесь. Вторая такая же фраза из десяти слов.",0,4000);
            session.acceptFinal("Итак, переходим дальше.",4000,5000);
            assertTrue(session.chunks.isEmpty());
            assertEquals(3,session.pending.size());
        }
        Store store2=new Store();store2.create("mk4","hash","live");
        try(var session=new Session("mk4","live",store2,new Models(false),new Llm())){
            session.clock.shutdownNow();session.generating=true;
            // 3 sentences × 12 words = 36 words ≥ 30: marker commits.
            StringBuilder big=new StringBuilder();
            for(int i=0;i<3;i++)big.append("Предложение с достаточным количеством слов для преодоления порога номер ").append(i).append(" продолжается. ");
            session.acceptFinal(big.toString(),0,6000);
            assertTrue(session.chunks.isEmpty());
            session.acceptFinal("Итак, переходим к следующей теме.",6000,7000);
            assertEquals(1,session.chunks.size());
            assertEquals(1,session.pending.size());
        }
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

    @Test void strongTopicShiftMarkersTrigger(){
        assertTrue(Text.startsWithMarker("Начнём с обзора архитектуры."));
        assertTrue(Text.startsWithMarker("Первая тема — постановка задачи."));
        assertTrue(Text.startsWithMarker("Следующий вопрос касается безопасности."));
        assertTrue(Text.startsWithMarker("Подведём итог по разделу."));
        assertTrue(Text.startsWithMarker("Подводя итог, отметим главное."));
        assertTrue(Text.startsWithMarker("Итоги эксперимента таковы."));
        assertTrue(Text.startsWithMarker("Вывод прост: локальная обработка."));
        assertTrue(Text.startsWithMarker("Отдельная тема — масштабирование."));
        assertTrue(Text.startsWithMarker("Поговорим о производительности."));
        assertTrue(Text.startsWithMarker("Давайте начнём с демонстрации."));
        assertTrue(Text.startsWithMarker("Переходим к практической части."));
    }

    @Test void riskyWeakMarkersStayExcluded(){
        assertFalse(Text.startsWithMarker("Кстати, об этом позже."));
        assertFalse(Text.startsWithMarker("Между прочим, важный момент."));
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
