package local.voicedeck;

import java.util.concurrent.*;

/** A stuck native call consumes one worker, never an unbounded queue or new threads. */
final class BoundedInference implements AutoCloseable {
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(1), runnable -> {
                Thread thread = new Thread(runnable, "bounded-asr");
                thread.setDaemon(true);
                return thread;
            }, new ThreadPoolExecutor.AbortPolicy());

    <T> T call(Callable<T> operation, long timeoutMs) throws Exception {
        Future<T> future = worker.submit(operation);
        try {
            return future.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException | InterruptedException error) {
            future.cancel(true);
            worker.purge();
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw error;
        } catch (ExecutionException error) {
            if (error.getCause() instanceof Exception cause) throw cause;
            throw error;
        }
    }

    boolean idle() { return worker.getActiveCount() == 0; }

    public void close() throws InterruptedException {
        worker.shutdownNow();
        worker.awaitTermination(1, TimeUnit.SECONDS);
    }
}
