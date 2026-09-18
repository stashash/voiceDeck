package local.voicedeck;

import io.vertx.core.json.*;
import java.sql.*;
import java.util.*;

/** Append-only event log. Acknowledgement follows durable commit. No audio is stored. */
public final class Store {
    private final String url = System.getenv("DB_URL");
    private final Map<String,JsonObject> sessions = new HashMap<>();
    private final Map<String,List<JsonObject>> logs = new HashMap<>();
    public boolean durable() { return url != null && !url.isBlank(); }
    private Connection connect() throws SQLException {
        return DriverManager.getConnection(url, Main.env("DB_USER","voicedeck"), Main.env("DB_PASSWORD","local-development-only"));
    }
    public void init() throws SQLException {
        if (!durable()) return;
        try (var c=connect(); var s=c.createStatement()) {
            s.execute("CREATE EXTENSION IF NOT EXISTS vector");
            s.execute("CREATE TABLE IF NOT EXISTS sessions(id text PRIMARY KEY, token_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), mode text NOT NULL)");
            s.execute("CREATE TABLE IF NOT EXISTS events(session_id text REFERENCES sessions(id) ON DELETE CASCADE, seq bigint NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(session_id,seq))");
            s.execute("CREATE TABLE IF NOT EXISTS embeddings(session_id text REFERENCES sessions(id) ON DELETE CASCADE, sent_id text NOT NULL, embedding vector NOT NULL, PRIMARY KEY(session_id,sent_id))");
        }
    }
    public synchronized void create(String id,String hash,String mode) throws SQLException {
        if (!durable()) { sessions.put(id,new JsonObject().put("id",id).put("token_hash",hash).put("mode",mode)); logs.put(id,new ArrayList<>()); return; }
        try(var c=connect();var p=c.prepareStatement("INSERT INTO sessions(id,token_hash,mode) VALUES(?,?,?)")) {p.setString(1,id);p.setString(2,hash);p.setString(3,mode);p.executeUpdate();}
    }
    public synchronized JsonObject session(String id) throws SQLException {
        if(!durable()) return sessions.get(id);
        try(var c=connect();var p=c.prepareStatement("SELECT token_hash,mode FROM sessions WHERE id=?")) {
            p.setString(1,id);try(var r=p.executeQuery()){return r.next()?new JsonObject().put("id",id).put("token_hash",r.getString(1)).put("mode",r.getString(2)):null;}
        }
    }
    public synchronized void append(String id,JsonObject event) throws SQLException {
        if(!durable()) {logs.get(id).add(event.copy());return;}
        try(var c=connect();var p=c.prepareStatement("INSERT INTO events(session_id,seq,payload) VALUES(?,?,?::jsonb)")) {
            p.setString(1,id);p.setLong(2,event.getLong("seq"));p.setString(3,event.encode());p.executeUpdate();
        }
    }
    public synchronized List<JsonObject> events(String id,long from) throws SQLException {
        if(!durable()) return logs.getOrDefault(id,List.of()).stream().filter(e->e.getLong("seq")>from).map(JsonObject::copy).toList();
        try(var c=connect();var p=c.prepareStatement("SELECT payload FROM events WHERE session_id=? AND seq>? ORDER BY seq")) {
            p.setString(1,id);p.setLong(2,from);try(var r=p.executeQuery()){List<JsonObject> out=new ArrayList<>();while(r.next())out.add(new JsonObject(r.getString(1)));return out;}
        }
    }
    public synchronized void delete(String id) throws SQLException {
        if(!durable()) {sessions.remove(id);logs.remove(id);return;}
        try(var c=connect();var p=c.prepareStatement("DELETE FROM sessions WHERE id=?")){p.setString(1,id);p.executeUpdate();}
    }
    public void embedding(String id,String sentId,float[] vector)throws SQLException {
        if(!durable()||vector==null)return;
        String value=Arrays.toString(vector);
        try(var c=connect();var p=c.prepareStatement("INSERT INTO embeddings(session_id,sent_id,embedding) VALUES(?,?,?::vector) ON CONFLICT(session_id,sent_id) DO UPDATE SET embedding=EXCLUDED.embedding")){p.setString(1,id);p.setString(2,sentId);p.setString(3,value);p.executeUpdate();}
    }
}
