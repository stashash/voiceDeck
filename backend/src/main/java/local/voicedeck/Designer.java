package local.voicedeck;

import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

/** HTTP-клиент сервиса designer: POST /live/slide. Локальный адрес обязателен, проверка как у Llm и EmbeddingClient.
 *  DESIGNER_URL пустой строкой означает «выключено»: конструктор пропускает и SSRF-проверку, и HTTP(S)-проверку. */
public final class Designer {
    private final HttpClient http;
    private final String url;
    private final boolean enabled;

    public Designer(){this(Main.env("DESIGNER_URL",""),HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build());}
    Designer(String url,HttpClient http){
        this.url=url;this.http=http;this.enabled=!url.isBlank();
        if(!enabled)return;
        URI uri=URI.create(url);
        if(!"http".equals(uri.getScheme())&&!"https".equals(uri.getScheme()))throw new IllegalArgumentException("DESIGNER_URL must use HTTP(S)");
        try{for(InetAddress ip:InetAddress.getAllByName(uri.getHost()))if(!EmbeddingClient.isLocalAddress(ip))throw new IllegalArgumentException("DESIGNER_URL must resolve inside the local network");}
        catch(UnknownHostException e){throw new IllegalArgumentException("Cannot resolve designer host",e);}
    }
    public boolean enabled(){return enabled;}
    /** designer жив, но модель в LM Studio ещё грузится: слайд появится после загрузки, сервис не сломан. */
    public static final class ModelLoading extends RuntimeException{ModelLoading(){super("model loading");}}
    /** Ответ 204 -> null («слайд не нужен»). Ответ 200 разбирается в поля события slide. */
    public JsonObject slide(String designSystemId,String chunkText,List<String> usedPatternIds)throws Exception {
        if(!enabled)throw new IllegalStateException("Designer disabled");
        var body=new JsonObject().put("design_system_id",designSystemId).put("chunk_text",chunkText).put("used_pattern_ids",new JsonArray(usedPatternIds));
        // Слайд из речи на Qwen идёт 4–5 с; когда модель занята сборкой колоды, дольше. 8 с обрывали такие слайды.
        var req=HttpRequest.newBuilder(URI.create(url+"/live/slide")).timeout(Duration.ofSeconds(15)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body.encode())).build();
        var res=http.send(req,HttpResponse.BodyHandlers.ofString());
        if(res.statusCode()==204)return null;
        if(res.statusCode()==503)throw new ModelLoading();
        if(res.statusCode()!=200)throw new IllegalStateException("Designer HTTP "+res.statusCode());
        return toSlide(new JsonObject(res.body()));
    }
    /** Сцена + html -> прежние поля slide (заголовок и тексты блоков по роли элемента) плюс pattern_id и html. */
    static JsonObject toSlide(JsonObject response) {
        JsonObject scene=response.getJsonObject("scene");
        String title=null;JsonArray bullets=new JsonArray();
        for(Object raw:scene.getJsonArray("elements",new JsonArray())){
            JsonObject el=(JsonObject)raw;
            if(!"text".equals(el.getString("type")))continue;
            String text=el.getString("text","");if(text.isBlank())continue;
            String role=el.getString("role","");
            if(title==null&&(role.equals("title")||role.equals("heading")))title=text;
            else if(role.equals("body"))bullets.add(text);
        }
        return new JsonObject().put("title",title).put("bullets",bullets).put("notes","").put("pattern_id",scene.getString("pattern_id")).put("html",response.getString("html"));
    }
}
