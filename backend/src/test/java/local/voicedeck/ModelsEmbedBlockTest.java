package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;

class ModelsEmbedBlockTest {
    @Test void joinBlockNullReturnsNull(){
        assertNull(Models.joinBlock(null));
    }

    @Test void joinBlockEmptyReturnsNull(){
        assertNull(Models.joinBlock(List.of()));
    }

    @Test void joinBlockSingleSentence(){
        assertEquals("один",Models.joinBlock(List.of("один")));
    }

    @Test void joinBlockTwoSentences(){
        assertEquals("один два",Models.joinBlock(List.of("один","два")));
    }

    @Test void joinBlockThreeSentences(){
        assertEquals("a b c",Models.joinBlock(List.of("a","b","c")));
    }

    @Test void joinBlockTakesLastThreeOfLongerList(){
        assertEquals("три четыре пять",Models.joinBlock(List.of("один","два","три","четыре","пять")));
    }

    @Test void joinBlockExactlyFourTakesLastThree(){
        assertEquals("б в г",Models.joinBlock(List.of("а","б","в","г")));
    }

    @Test void embedBlockEmptyReturnsNull()throws Exception{
        var m=new Models(false);
        assertNull(m.embedBlock(null));
        assertNull(m.embedBlock(List.of()));
    }

    @Test void embedBlockSingleInDemoModeReturnsNull()throws Exception{
        var m=new Models(false);
        // Demo mode has embeddingBackend="disabled", embed returns null upstream.
        assertNull(m.embedBlock(List.of("один")));
    }
}
