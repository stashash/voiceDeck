package local.voicedeck;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EditorAudioTest {
    @Test void editorPaddingIsBoundedBySessionPriorSegmentAndRing(){
        assertEquals(0,Audio.editorSegmentStart(2144,0,40000,320000));
        assertEquals(16800,Audio.editorSegmentStart(20000,0,40000,320000));
        assertEquals(19000,Audio.editorSegmentStart(20000,19000,40000,320000));
        assertEquals(7000,Audio.editorSegmentStart(10000,0,17000,10000));
    }
    @Test void editorRetainsFullVadSegmentEvenWhenSpeechDetectionIsLate(){
        assertEquals(0,Audio.completedSegmentSkip(true,0,24000,32000));
        assertEquals(0,Audio.completedSegmentSkip(true,16000,40000,16000));
    }
    @Test void liveGenerationWindowBehaviorIsUnchanged(){
        assertEquals(24000,Audio.completedSegmentSkip(false,0,24000,32000));
        assertEquals(16000,Audio.completedSegmentSkip(false,16000,40000,16000));
        assertEquals(0,Audio.completedSegmentSkip(false,16000,-1,32000));
        assertEquals(0,Audio.completedSegmentSkip(false,16000,12000,32000));
    }
}
