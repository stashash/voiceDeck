package local.voicedeck;

import org.junit.jupiter.api.Test;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class MainOriginTest {
    private static final Set<String> ALLOWED=Set.of("https://demo.example");

    @Test void allowsSameOriginRequestsForStaticAssets(){
        assertTrue(Main.allowedOrigin("http://localhost:8088",ALLOWED,"http","localhost:8088"));
        assertTrue(Main.allowedOrigin("http://127.0.0.1",ALLOWED,"http","127.0.0.1"));
        assertTrue(Main.allowedOrigin("https://demo.example",ALLOWED,"http","app:8080"));
        assertTrue(Main.allowedOrigin(null,ALLOWED,"http","localhost:8088"));
    }

    @Test void rejectsForeignOriginsAndMalformedOriginValues(){
        assertFalse(Main.allowedOrigin("https://attacker.example",ALLOWED,"http","localhost:8088"));
        assertFalse(Main.allowedOrigin("http://localhost:8088.evil.example",ALLOWED,"http","localhost:8088"));
        assertFalse(Main.allowedOrigin("http://localhost:8088/path",ALLOWED,"http","localhost:8088"));
        assertFalse(Main.allowedOrigin("null",ALLOWED,"http","localhost:8088"));
    }
}
