package local.voicedeck;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class AllowedOriginsTest {
    @Test void acceptsAdditionalOriginsWithoutReplacingLocalOrigin() {
        Set<String> origins=new HashSet<>();
        Main.addAllowedOrigin(origins,"http://localhost:8088");
        Main.addAllowedOrigin(origins,"https://demo.example.test/");

        assertEquals(3,origins.size());
        assertTrue(origins.contains("http://localhost:8088"));
        assertTrue(origins.contains("http://127.0.0.1:8088"));
        assertTrue(origins.contains("https://demo.example.test"));
    }

    @Test void exposesDirectDesignerOnlyToAllowedLoopbackPages() {
        Set<String> origins=new HashSet<>();
        Main.addAllowedOrigin(origins,"http://localhost:8088");
        assertEquals("https://demo.example.test http://localhost:8090",
            Main.browserDesignerSources("localhost:8088","https://demo.example.test",origins));
        assertEquals("https://demo.example.test",
            Main.browserDesignerSources("demo.example.test","https://demo.example.test",origins));
    }
}
