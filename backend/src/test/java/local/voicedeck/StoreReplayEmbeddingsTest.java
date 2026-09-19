package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class StoreReplayEmbeddingsTest {
    @Test void parsesPgVectorFloats(){
        float[] v=Store.parsePgVector("[0.1, 0.2, 0.3]");
        assertEquals(3,v.length);
        assertEquals(0.1f,v[0],1e-6);
        assertEquals(0.2f,v[1],1e-6);
        assertEquals(0.3f,v[2],1e-6);
    }

    @Test void parsesPgVectorNegativeAndIntegers(){
        float[] v=Store.parsePgVector("[1.5, -2.5, 3.0]");
        assertEquals(3,v.length);
        assertEquals(1.5f,v[0],1e-6);
        assertEquals(-2.5f,v[1],1e-6);
        assertEquals(3.0f,v[2],1e-6);
    }

    @Test void parsesEmptyVector(){
        assertEquals(0,Store.parsePgVector("[]").length);
    }

    @Test void parsesNoSpaces(){
        float[] v=Store.parsePgVector("[1,2,3]");
        assertEquals(3,v.length);
        assertEquals(1f,v[0]);
        assertEquals(3f,v[2]);
    }

    @Test void rejectsMalformed(){
        assertThrows(IllegalArgumentException.class,()->Store.parsePgVector(""));
        assertThrows(IllegalArgumentException.class,()->Store.parsePgVector("not a vector"));
        assertThrows(IllegalArgumentException.class,()->Store.parsePgVector("[1,2"));
        assertThrows(IllegalArgumentException.class,()->Store.parsePgVector(null));
    }

    @Test void inMemoryModeReturnsEmpty()throws Exception{
        var store=new Store();
        store.create("test","hash","demo");
        // In-memory store has no persistent embeddings; embeddingsOf returns empty.
        assertTrue(store.embeddingsOf("test").isEmpty());
    }
}
