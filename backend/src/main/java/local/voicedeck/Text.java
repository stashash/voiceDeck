package local.voicedeck;

import java.util.*;
import java.util.regex.Pattern;

public final class Text {
    private Text() {}
    private static final Pattern ABBR = Pattern.compile("(?iu).*(?<!\\p{L})(?:т\\.е|т\\.д|т\\.п|т\\.к|рис|стр|им|руб|г|гг|см|др|проф|доц|ул|д|кв|[а-яa-z])\\.$");
    public static List<String> sentences(String text) {
        List<String> result = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c != '.' && c != '!' && c != '?' && c != '\n') continue;
            if (c == '.' && i > 0 && i + 1 < text.length() && Character.isDigit(text.charAt(i-1)) && Character.isDigit(text.charAt(i+1))) continue;
            if (c == '.' && ABBR.matcher(text.substring(start, i+1).trim()).matches()) continue;
            int next = i + 1;
            while (next < text.length() && (Character.isWhitespace(text.charAt(next)) || ".!?»\"".indexOf(text.charAt(next)) >= 0)) next++;
            if (next < text.length() && !Character.isUpperCase(text.charAt(next)) && c != '\n') continue;
            String sentence = text.substring(start, i+1).trim();
            if (!sentence.isEmpty()) result.add(sentence);
            start = i+1;
        }
        if (!text.substring(start).isBlank()) result.add(text.substring(start).trim());
        return result;
    }
    public static int words(String text) { return text.isBlank() ? 0 : text.trim().split("\\s+").length; }
    public static double cosine(float[] a, float[] b) {
        if (a == null || b == null || a.length != b.length) return 1;
        double dot=0, aa=0, bb=0;
        for (int i=0;i<a.length;i++) { dot+=a[i]*b[i]; aa+=a[i]*a[i]; bb+=b[i]*b[i]; }
        return aa==0 || bb==0 ? 1 : dot/Math.sqrt(aa*bb);
    }
    public static String deduplicate(String previous, String current) {
        String[] a=previous.trim().split("\\s+"), b=current.trim().split("\\s+");
        for (int n=Math.min(12,Math.min(a.length,b.length));n>=2;n--) {
            boolean same=true;
            for(int i=0;i<n;i++) if(!a[a.length-n+i].replaceAll("\\p{P}","").equalsIgnoreCase(b[i].replaceAll("\\p{P}",""))) same=false;
            if(same) return String.join(" ",Arrays.copyOfRange(b,n,b.length));
        }
        return current;
    }
    public static String escape(String s) { return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;").replace("'","&#39;"); }
}
