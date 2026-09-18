package local.voicedeck;
import java.util.*;
import java.util.concurrent.*;
/** Bounded rolling distributions; values are milliseconds on the server clock. */
public final class Metrics {
 private static final Map<String,ArrayDeque<Long>> stages=new ConcurrentHashMap<>();
 private Metrics(){}
 public static void observe(String name,long value){var samples=stages.computeIfAbsent(name,k->new ArrayDeque<>());synchronized(samples){samples.add(Math.max(0,value));if(samples.size()>4096)samples.removeFirst();}}
 public static String prometheus(){StringBuilder out=new StringBuilder();stages.forEach((name,samples)->{long[] sorted;synchronized(samples){sorted=samples.stream().mapToLong(Long::longValue).sorted().toArray();}if(sorted.length==0)return;String metric="voicedeck_"+name+"_milliseconds";out.append("# TYPE ").append(metric).append(" summary\n");for(double q:new double[]{.5,.95,.99})out.append(metric).append("{quantile=\"").append(q).append("\"} ").append(sorted[(int)Math.ceil(sorted.length*q)-1]).append('\n');out.append(metric).append("_count ").append(sorted.length).append('\n');});return out.toString();}
}
