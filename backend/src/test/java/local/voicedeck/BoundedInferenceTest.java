package local.voicedeck;

import org.junit.jupiter.api.Test;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class BoundedInferenceTest {
    @Test void hungNativeCallHasBoundedWaitAndDoesNotSpawnMoreWorkers() throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger calls = new AtomicInteger();
        try (var inference = new BoundedInference()) {
            assertThrows(TimeoutException.class, () -> inference.call(() -> {
                calls.incrementAndGet();
                while (release.getCount() > 0) {
                    try { release.await(); } catch (InterruptedException ignored) { }
                }
                return "late";
            }, 40));
            assertThrows(TimeoutException.class, () -> inference.call(() -> {calls.incrementAndGet(); return "queued";}, 40));
            assertEquals(1, calls.get());
            release.countDown();
        } finally {release.countDown();}
    }
    @Test void exceptionsPropagateAndNextCommandWorks() throws Exception {
        try (var inference = new BoundedInference()) {
            assertThrows(IllegalStateException.class, () -> inference.call(() -> {throw new IllegalStateException("failed");}, 500));
            assertEquals("ok", inference.call(() -> "ok", 500));
        }
    }
}
