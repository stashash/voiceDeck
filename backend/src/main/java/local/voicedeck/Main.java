package local.voicedeck;

import io.vertx.core.*;
import io.vertx.core.http.*;
import io.vertx.core.json.*;
import io.vertx.ext.web.*;
import io.vertx.ext.web.handler.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;

public final class Main {
    static String env(String key,String fallback){String value=System.getenv(key);return value==null||value.isBlank()?fallback:value;}
    private static String hash(String token){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
    public static void main(String[] args)throws Exception {
        boolean live=env("MODE","demo").equals("live");
        Store store=new Store();store.init();Models models=new Models(live);Llm llm=new Llm();Designer designer=new Designer();
        Vertx vertx=Vertx.vertx();Router router=Router.router(vertx);
        Map<String,Session> sessions=new ConcurrentHashMap<>();
        String allowedOrigin=env("ALLOWED_ORIGIN","http://localhost:8080");
        Set<String> origins=new HashSet<>(List.of(allowedOrigin,allowedOrigin.replace("localhost","127.0.0.1")));
        // Страницы «Колода», «Шаблон» и «Сцена» ходят из браузера в сервис designer: его адрес разрешён для запросов и картинок слайдов.
        String designerPublic=env("DESIGNER_PUBLIC_URL","http://localhost:8090");
        router.route().handler(ctx->{
            ctx.response().putHeader("X-Content-Type-Options","nosniff").putHeader("Referrer-Policy","no-referrer").putHeader("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' "+designerPublic+" "+String.join(" ",origins.stream().map(o->o.replaceFirst("^http","ws")).toList())+"; worker-src 'self'; img-src 'self' data: blob: "+designerPublic+"; font-src 'self' data:; frame-src 'self' about: data:; frame-ancestors 'none'");
            String origin=ctx.request().getHeader("Origin");
            if(origin!=null&&!origins.contains(origin)){ctx.response().setStatusCode(403).end("Origin not allowed");return;}ctx.next();
        });
        router.get("/health").handler(ctx->ctx.json(new JsonObject().put("status","ready").put("mode",live?"live":"demo").put("asr",live?"sherpa-onnx":"not-loaded").put("embeddings",models.embeddingStatus()).put("storage",store.durable()?"postgres":"memory-volatile").put("audio_stored",false)));
        router.get("/metrics").handler(ctx->ctx.response().putHeader("Content-Type","text/plain; version=0.0.4").end(Metrics.prometheus()));
        router.post("/api/sessions").blockingHandler(ctx->{
            try {
                if(sessions.size()>=8){ctx.response().setStatusCode(429).end("Maximum 8 active sessions");return;}
                byte[] secret=new byte[32];new SecureRandom().nextBytes(secret);String token=Base64.getUrlEncoder().withoutPadding().encodeToString(secret),id=UUID.randomUUID().toString();
                String mode=live?"live":"demo";store.create(id,hash(token),mode);Session session=new Session(id,mode,store,models,llm,designer);sessions.put(id,session);
                ctx.response().putHeader("Cache-Control","no-store");ctx.json(new JsonObject().put("id",id).put("token",token).put("mode",mode));
            }catch(Exception e){ctx.fail(e);}
        },false);
        Handler<RoutingContext> authenticate=ctx->{
            String id=ctx.pathParam("id"),auth=ctx.request().getHeader("Authorization");
            try {
                JsonObject record=store.session(id);
                if(record==null||auth==null||!auth.startsWith("Bearer ")||!MessageDigest.isEqual(hash(auth.substring(7)).getBytes(StandardCharsets.UTF_8),record.getString("token_hash").getBytes(StandardCharsets.UTF_8))){ctx.response().setStatusCode(401).end("Unauthorized");return;}
                Session s=sessions.get(id);if(s==null){s=new Session(id,record.getString("mode"),store,models,llm,designer);Session existing=sessions.putIfAbsent(id,s);if(existing!=null){s.close();s=existing;}}
                s.lastAccess=System.currentTimeMillis();ctx.put("session",s);ctx.next();
            }catch(Exception e){ctx.fail(e);}
        };
        router.route("/api/sessions/:id/*").blockingHandler(authenticate,false);
        router.get("/api/sessions/:id/events").blockingHandler(ctx->{try{long from=Long.parseLong(ctx.request().getParam("from")==null?"0":ctx.request().getParam("from"));if(from<0)throw new IllegalArgumentException();ctx.json(new JsonArray(store.events(ctx.pathParam("id"),from)));}catch(NumberFormatException e){ctx.response().setStatusCode(400).end("Invalid cursor");}catch(Exception e){ctx.fail(e);}},false);
        router.get("/api/sessions/:id/snapshot").handler(ctx->{Session s=ctx.get("session");s.snapshot(ctx::json);});
        router.get("/api/sessions/:id/export").handler(ctx->{Session s=ctx.get("session");s.snapshot(snapshot->{
            if("json".equals(ctx.request().getParam("format"))){ctx.response().putHeader("Content-Disposition","attachment; filename=voicedeck.json");ctx.json(snapshot);return;}
            StringBuilder html=new StringBuilder("<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>VoiceDeck — презентация</title><style>body{background:#eef2f0;color:#15382c;font:24px system-ui;margin:0}section{background:white;box-sizing:border-box;max-width:1100px;min-height:620px;margin:32px auto;padding:70px;border-top:8px solid #2c8060;break-after:page}h1{font-size:48px}li{margin:24px 0}small{color:#6b7c74}aside{font-size:18px;margin-top:40px}@media print{body{background:white}section{margin:0;height:100vh;max-width:none}aside{display:none}}</style>");
            Map<String,JsonObject> deck=new HashMap<>();for(Object raw:snapshot.getJsonArray("slides")){JsonObject slide=(JsonObject)raw;deck.put(slide.getString("chunk_id"),slide);}
            for(Object raw:snapshot.getJsonArray("chunks")){JsonObject c=(JsonObject)raw,slide=deck.get(c.getString("id"));if(slide==null||slide.getValue("title")==null)continue;html.append("<section><small>VOICEDECK · ").append(c.getLong("t0")/1000).append("–").append(c.getLong("t1")/1000).append(" с</small><h1>").append(Text.escape(slide.getString("title"))).append("</h1><ul>");for(Object bullet:slide.getJsonArray("bullets"))html.append("<li>").append(Text.escape(bullet.toString())).append("</li>");html.append("</ul><aside>").append(Text.escape(slide.getString("notes",""))).append("</aside></section>");}
            html.append("</html>");ctx.response().putHeader("Content-Type","text/html; charset=utf-8").putHeader("Content-Disposition","attachment; filename=voicedeck.html").end(html.toString());
        });});
        router.delete("/api/sessions/:id/data").blockingHandler(ctx->{try{Session s=ctx.get("session");s.close();sessions.remove(s.id);store.delete(s.id);ctx.response().setStatusCode(204).end();}catch(Exception e){ctx.fail(e);}},false);
        // Browser WebSocket API cannot set Authorization. Send bearer token in the first frame, never a URL.
        router.get("/ws/session").handler(ctx->ctx.request().toWebSocket().onSuccess(ws->{
            long timeout=vertx.setTimer(5000,x->ws.close((short)1008,"Authentication required"));
            final Session[] bound={null};final boolean[] authenticating={false};
            ws.setWriteQueueMaxSize(2*1024*1024);
            ws.textMessageHandler(raw->{
                if(raw.length()>20000){ws.close((short)1009,"Message too large");return;}
                JsonObject message;try{message=new JsonObject(raw);}catch(Exception e){ws.close((short)1007,"Invalid JSON");return;}
                if(bound[0]!=null){if(bound[0].socket!=ws){ws.close();return;}bound[0].text(message);return;}
                if(authenticating[0])return;authenticating[0]=true;
                vertx.<Session>executeBlocking(()->{
                    if(!message.fieldNames().equals(Set.of("type","session_id","token","from"))||!"auth".equals(message.getString("type")))throw new IllegalArgumentException("Invalid authentication");
                    String id=message.getString("session_id");JsonObject record=store.session(id);
                    if(record==null||!MessageDigest.isEqual(hash(message.getString("token","")).getBytes(StandardCharsets.UTF_8),record.getString("token_hash").getBytes(StandardCharsets.UTF_8)))throw new IllegalArgumentException("Unauthorized");
                    Session s=sessions.get(id);if(s==null){s=new Session(id,record.getString("mode"),store,models,llm,designer);Session existing=sessions.putIfAbsent(id,s);if(existing!=null){s.close();s=existing;}}return s;
                },false).onSuccess(s->{if(ws.isClosed())return;vertx.cancelTimer(timeout);bound[0]=s;s.attach(ws,message.getLong("from",0L));}).onFailure(e->ws.close((short)1008,"Unauthorized"));
            });
            ws.binaryMessageHandler(b->{if(bound[0]==null||bound[0].socket!=ws){ws.close((short)1008,"Authenticate first");return;}bound[0].acceptAudio(b.getBytes());});
            ws.closeHandler(v->{vertx.cancelTimer(timeout);if(bound[0]!=null&&bound[0].socket==ws)bound[0].socket=null;});
            ws.exceptionHandler(e->{if(!ws.isClosed())ws.close();});
        }));
        router.route().handler(StaticHandler.create("webroot").setCachingEnabled(false));
        router.route().failureHandler(ctx->{System.err.println("Request failed: "+ctx.failure());ctx.response().setStatusCode(500).end("Operation failed; inspect server logs");});
        vertx.setPeriodic(1000,t->sessions.values().forEach(s->s.submit(()->s.wire(s.metrics()))));
        vertx.setPeriodic(60000,t->sessions.values().removeIf(s->{if(s.socket==null&&System.currentTimeMillis()-s.lastAccess>1800000){s.close();return true;}return false;}));
        vertx.createHttpServer(new HttpServerOptions().setMaxWebSocketFrameSize(32768).setMaxWebSocketMessageSize(32768)).requestHandler(router).listen(Integer.parseInt(env("PORT","8080")),env("HOST","0.0.0.0")).toCompletionStage().toCompletableFuture().join();
        Runtime.getRuntime().addShutdownHook(new Thread(()->{sessions.values().forEach(Session::close);try{models.close();}catch(Exception ignored){}vertx.close();}));
        System.out.println("VoiceDeck ready at http://localhost:"+env("PORT","8080")+"; mode="+(live?"live":"demo"));
    }
}
