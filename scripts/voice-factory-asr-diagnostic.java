import local.voicedeck.Models;
import local.voicedeck.Audio;
import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

/** Standalone, read-only diagnostic using the installed production Models/Audio classes. */
class VoiceFactoryAsrDiagnostic {
    static Object call(Object object, String method, Object... arguments) throws Exception {
        for (var candidate : object.getClass().getMethods()) {
            if (candidate.getName().equals(method) && candidate.getParameterCount() == arguments.length) {
                try { return candidate.invoke(object, arguments); } catch (IllegalArgumentException ignored) {}
            }
        }
        throw new NoSuchMethodException(method);
    }

    static float[] wav(Path path) throws Exception {
        byte[] bytes = Files.readAllBytes(path);
        ByteBuffer input = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        if (!new String(bytes, 0, 4).equals("RIFF") || !new String(bytes, 8, 4).equals("WAVE")) throw new IllegalArgumentException("WAV required");
        boolean valid = false;
        for (int offset = 12; offset + 8 <= bytes.length;) {
            int size = input.getInt(offset + 4), start = offset + 8;
            String id = new String(bytes, offset, 4);
            if (size < 0 || start + size > bytes.length) throw new IllegalArgumentException("Truncated WAV");
            if (id.equals("fmt ")) valid = input.getShort(start) == 1 && input.getShort(start + 2) == 1 && input.getInt(start + 4) == 16000 && input.getShort(start + 14) == 16;
            if (id.equals("data")) {
                if (!valid || size % 2 != 0) throw new IllegalArgumentException("16 kHz mono PCM16 required");
                float[] pcm = new float[size / 2];
                for (int i = 0; i < pcm.length; i++) pcm[i] = input.getShort(start + 2 * i) / 32768f;
                return pcm;
            }
            offset = start + size + size % 2;
        }
        throw new IllegalArgumentException("No PCM data");
    }

    static JsonObject diagnose(Models models, Path file, int trailingSamples) throws Exception {
        float[] pcm = wav(file);
        JsonObject result = new JsonObject().put("file", file.toString()).put("samples", pcm.length).put("durationMs", pcm.length / 16.0);
        result.put("fullPcmDecode", models.decode(pcm, true));
        Object vad = models.newVad();
        JsonArray segments = new JsonArray(), detections = new JsonArray(), production = new JsonArray();
        long phraseStart = -1, samples = 0, lastBufferedEnd = 0;
        float[] padded = Arrays.copyOf(pcm, ((pcm.length + trailingSamples + 511) / 512) * 512);
        try (Audio audio = new Audio(models, new Audio.Listener() {
            public void partial(String text, long t0, long t1) { production.add(new JsonObject().put("type", "partial").put("text", text).put("t0", t0).put("t1", t1)); }
            public void finish(String text, long t0, long t1) { production.add(new JsonObject().put("type", "final").put("text", text).put("t0", t0).put("t1", t1)); }
            public void warning(String message) { production.add(new JsonObject().put("type", "warning").put("message", message)); }
        })) {
            audio.editorMode(true);
            for (int offset = 0; offset < padded.length; offset += 512) {
                float[] frame = Arrays.copyOfRange(padded, offset, offset + 512);
                audio.accept(new Audio.Packet(offset / 512 + 1, offset, frame));
                samples += 512;
                call(vad, "acceptWaveform", frame);
                if ((boolean) call(vad, "isSpeechDetected") && phraseStart < 0) {
                    phraseStart = Math.max(0, samples - 4096);
                    detections.add(new JsonObject().put("detectedAtSample", samples).put("heuristicPhraseStart", phraseStart).put("detectedAtMs", samples / 16.0));
                }
                while (!(boolean) call(vad, "empty")) {
                    Object segment = call(vad, "front");
                    float[] speech = (float[]) call(segment, "getSamples");
                    long start = ((Number) call(segment, "getStart")).longValue();
                    int skip = phraseStart >= 0 && start < phraseStart ? (int) Math.min(speech.length, phraseStart - start) : 0;
                    JsonObject row = new JsonObject().put("startSample", start).put("samples", speech.length)
                        .put("startMs", start / 16.0).put("endMs", (start + speech.length) / 16.0)
                        .put("heuristicPhraseStartSample", phraseStart).put("wouldCropSamples", skip).put("wouldCropMs", skip / 16.0)
                        .put("fullVadDecode", models.decode(speech, true));
                    row.put("croppedVadDecode", skip < speech.length ? models.decode(Arrays.copyOfRange(speech, skip, speech.length), true) : "");
                    long bufferedStart = Math.max(lastBufferedEnd, Math.max(Math.max(0, samples - 16000 * 20), start - 3200));
                    long bufferedEnd = Math.min(samples, start + speech.length + 2560);
                    row.put("bufferedStartMs", bufferedStart / 16.0).put("bufferedEndMs", bufferedEnd / 16.0)
                        .put("bufferedDecode", bufferedEnd > bufferedStart ? models.decode(Arrays.copyOfRange(padded, (int) bufferedStart, (int) bufferedEnd), true) : "");
                    lastBufferedEnd = bufferedEnd;
                    segments.add(row);
                    call(vad, "pop"); phraseStart = -1;
                }
            }
            audio.flush();
            call(vad, "flush");
            while (!(boolean) call(vad, "empty")) {
                Object segment = call(vad, "front");
                float[] speech = (float[]) call(segment, "getSamples");
                long start = ((Number) call(segment, "getStart")).longValue();
                long bufferedStart = Math.max(lastBufferedEnd, Math.max(Math.max(0, samples - 16000 * 20), start - 3200));
                long bufferedEnd = Math.min(samples, start + speech.length + 2560);
                segments.add(new JsonObject().put("source", "native-flush").put("startSample", start)
                    .put("samples", speech.length).put("startMs", start / 16.0).put("endMs", (start + speech.length) / 16.0)
                    .put("fullVadDecode", models.decode(speech, true))
                    .put("bufferedStartMs", bufferedStart / 16.0).put("bufferedEndMs", bufferedEnd / 16.0)
                    .put("bufferedDecode", bufferedEnd > bufferedStart ? models.decode(Arrays.copyOfRange(padded, (int) bufferedStart, (int) bufferedEnd), true) : ""));
                lastBufferedEnd = bufferedEnd;
                call(vad, "pop");
            }
        } finally { call(vad, "release"); }
        return result.put("trailingSilenceMs", trailingSamples / 16.0).put("vadDetections", detections).put("vadSegments", segments).put("productionAudioEvents", production);
    }

    public static void main(String[] args) throws Exception {
        JsonArray rows = new JsonArray();
        try (Models models = new Models(true, null)) {
            for (int i = 1; i < args.length; i++) {
                rows.add(diagnose(models, Path.of(args[i]), 16000));
                rows.add(diagnose(models, Path.of(args[i]), 0));
            }
        }
        Files.writeString(Path.of(args[0]), new JsonObject().put("cases", rows).encodePrettily());
        System.out.println(new JsonObject().put("report", args[0]).put("cases", rows.size()).encode());
    }
}
