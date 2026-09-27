package local.voicedeck;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EditorUtteranceTest {
    @Test void editorKeepsCompleteUtteranceAndDoesNotGenerateChunks() throws Exception {
        Store store=new Store();store.create("editor-test","hash","demo");
        try(var session=new Session("editor-test","demo",store,new Models(false),new Llm())) {
            session.clock.shutdownNow();session.editorMode=true;
            String text="Добавь заголовок. Затем три карточки.";
            session.acceptFinal(text,0,1000);
            var event=store.events("editor-test",0).stream().filter(e->"editor_utterance".equals(e.getString("type"))).findFirst().orElseThrow();
            assertEquals(text,event.getString("text"));assertNotNull(event.getString("utterance_id"));
            assertEquals(0L,event.getLong("t0"));assertEquals(1000L,event.getLong("t1"));
            assertTrue(session.sentences.isEmpty());assertTrue(session.pending.isEmpty());assertTrue(session.chunks.isEmpty());
        }
    }

    @Test void keepsAudioOffsetsForFrontendContextChecks(){
        var event=Session.editorUtterance("Replace",32,1800);
        assertEquals("Replace",event.getString("text"));
        assertEquals(32L,event.getLong("t0"));
        assertEquals(1800L,event.getLong("t1"));
        assertNotEquals(event.getString("utterance_id"),Session.editorUtterance("Replace",32,1800).getString("utterance_id"));
    }
}
