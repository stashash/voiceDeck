package local.voicedeck;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class ModelsChunkSizeConfigTest {
    @Test void defaultsMatchSegmentationAnalysis()throws Exception{
        var m=new Models(false); // demo mode → empty config → defaults apply
        assertEquals(60,m.chunkSizeMin());
        assertEquals(200,m.chunkSizeTarget());
        assertEquals(300,m.chunkSizeMax());
        assertEquals(500,m.chunkSizeEmergency());
        assertEquals(250,m.chunkCoalesceMax());
    }

    @Test void sizeTargetsIncreaseProgressively()throws Exception{
        var m=new Models(false);
        assertTrue(m.chunkSizeMin() < m.chunkSizeTarget());
        assertTrue(m.chunkSizeTarget() < m.chunkSizeMax());
        assertTrue(m.chunkSizeMax() < m.chunkSizeEmergency());
    }

    @Test void coalesceLimitAboveTargetAndBelowEmergency()throws Exception{
        var m=new Models(false);
        assertTrue(m.chunkCoalesceMax() >= m.chunkSizeTarget());
        assertTrue(m.chunkCoalesceMax() < m.chunkSizeEmergency());
    }
}
