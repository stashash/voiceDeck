package local.voicedeck;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import io.vertx.core.json.*;
import java.nio.*;
import java.util.*;

class PipelineTest {
 @Test void sentenceAbbreviationsAndDecimals(){
  assertEquals(List.of("И.И. Иванов показал рис. 3 и значение 3.14.","Это важно!"),Text.sentences("И.И. Иванов показал рис. 3 и значение 3.14. Это важно!"));
  assertEquals(1,Text.sentences("Это т.е. пояснение и т.д. в одной фразе.").size());
  assertEquals(2,Text.sentences("Первый вопрос? Второй ответ.").size());
 }
 @Test void audioContract(){
  var bytes=ByteBuffer.allocate(1040).order(ByteOrder.LITTLE_ENDIAN);bytes.putLong(1).putLong(0).putShort(Short.MIN_VALUE).putShort(Short.MAX_VALUE);
  var p=Audio.Packet.parse(bytes.array());assertEquals(1,p.seq());assertEquals(-1,p.samples()[0]);assertTrue(p.samples()[1]<1);assertEquals(512,p.samples().length);
  assertThrows(IllegalArgumentException.class,()->Audio.Packet.parse(new byte[1039]));
  bytes.putLong(0,-1);assertThrows(IllegalArgumentException.class,()->Audio.Packet.parse(bytes.array()));
 }
 @Test void overlappingSpeech(){assertEquals("Новая тема",Text.deduplicate("Один два три.","два три Новая тема"));assertEquals("три четыре",Text.deduplicate("Один два три","три четыре"));}
 @Test void revisionsAndReplay()throws Exception {
  Store store=new Store();store.create("test","hash","demo");var models=new Models(false);var llm=new Llm();
  try(var session=new Session("test","demo",store,models,llm)){
   session.clock.shutdownNow();
   session.acceptFinal("Первая тема раскрыта. Вторая тема появилась.",0,1000);session.commit("test");
   JsonObject chunk=session.orderedChunks().getFirst();String id=chunk.getString("id");
   var revision=new JsonObject().put("type","revise").put("operation","split").put("chunk_id",id).put("rev",2).put("split_at",1);
   session.revise(revision);assertEquals(2,session.chunks.size());long seq=session.seq;
   session.revise(revision);assertEquals(seq,session.seq);
   session.revise(new JsonObject().put("type","revise").put("operation","merge").put("chunk_id",id).put("rev",3).put("split_at",0));assertEquals(1,session.chunks.size());
   assertEquals(2,session.chunks.get(id).getJsonArray("sentence_ids").size());
   try(var restored=new Session("test","demo",store,models,llm)){restored.clock.shutdownNow();assertEquals(session.seq,restored.seq);assertEquals(session.sentences,restored.sentences);assertEquals(session.chunks,restored.chunks);assertTrue(restored.pending.isEmpty());}
  }
 }
 @Test void deadlineAndRevisionWindow()throws Exception {
  Store store=new Store();store.create("time","hash","demo");
  try(var session=new Session("time","demo",store,new Models(false),new Llm())){
   session.clock.shutdownNow();session.acceptFinal("Завершённая мысль.",0,100);session.epoch=System.currentTimeMillis()-3000;session.generating=true;session.tick();assertEquals(1,session.chunks.size());
   var c=session.orderedChunks().getFirst();c.put("updated_at",System.currentTimeMillis()-180001);long seq=session.seq;
   session.revise(new JsonObject().put("type","revise").put("operation","confirm").put("chunk_id",c.getString("id")).put("rev",2).put("split_at",0));assertEquals(seq,session.seq);
  }
 }
 @Test void rejectInvalidLlmOutput(){
  Llm.validateSlide(new JsonObject().put("title",null).put("bullets",new JsonArray()).put("notes",""));
  assertThrows(IllegalArgumentException.class,()->Llm.validateSlide(new JsonObject().put("title",42).put("bullets",new JsonArray()).put("notes","")));
  assertThrows(IllegalArgumentException.class,()->Llm.validateSlide(new JsonObject().put("title","Title").put("bullets",new JsonArray().add(4)).put("notes","")));
 }
 @Test void sentencesCapCommitsTwelveSentences()throws Exception {
  Store store=new Store();store.create("sent","hash","demo");
  try(var session=new Session("sent","demo",store,new Models(false),new Llm())){
   session.clock.shutdownNow();session.generating=true;
   StringBuilder text=new StringBuilder();
   for(int i=0;i<12;i++)text.append("Короткая фраза номер ").append(i).append(". ");
   session.acceptFinal(text.toString(),0,12000); // 36 words < target(120), 12 sentences = cap
   assertTrue(session.chunks.isEmpty());
   session.epoch=System.currentTimeMillis();session.lastFinalWall=System.currentTimeMillis()-200; // >100 ms pause, <600
   session.tick();
   assertEquals(1,session.chunks.size());
   assertEquals("sentences-cap",session.orderedChunks().getFirst().getString("reason"));
  }
 }
 @Test void chunkCarriesReasonField()throws Exception {
  Store store=new Store();store.create("reason","hash","demo");
  try(var session=new Session("reason","demo",store,new Models(false),new Llm())){
   session.clock.shutdownNow();session.generating=true;
   session.acceptFinal("Первая тема раскрыта полностью.",0,1000);session.commit("flush");
   JsonObject chunk=session.orderedChunks().getFirst();
   assertEquals("flush",chunk.getString("reason"));
   assertEquals("flush",session.store.events("reason",0).stream().filter(e->e.getString("type").equals("chunk")).findFirst().get().getString("reason"));
  }
 }
 @Test void shortSpeechContinuationsBecomeOneMeaningfulChunk()throws Exception {
  Store store=new Store();store.create("meaning","hash","live");
  try(var session=new Session("meaning","live",store,new Models(false),new Llm())){
   session.clock.shutdownNow();session.generating=true;
   session.acceptFinal("Я хочу рассказать",0,1800);session.commit("test");
   session.acceptFinal("как работает локальное распознавание.",2200,5000);session.commit("test");
   assertEquals(1,session.chunks.size());assertEquals(2,session.orderedChunks().getFirst().getJsonArray("sentence_ids").size());
   session.acceptFinal("Следующая тема после длинной паузы.",10000,13000);session.commit("test");assertEquals(2,session.chunks.size());
  }
 }
}
