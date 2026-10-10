package cn.shiying.mobile;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** One visible collection per download batch; individual owned file jobs remain intact. */
final class AlbumRecords {
    private static final Pattern FILE=Pattern.compile("^(.* \\d{8}_\\d{6}_\\d{3})_(\\d{3}|正文)\\.[^.]+$");
    private static final Pattern SUFFIX=Pattern.compile(" · (?:图片 \\d+/\\d+|正文)$");
    static boolean isAlbum(JSONObject record) { return record.optBoolean("album"); }
    static String batch(JSONObject record) {
        if (!record.optString("albumBatch").isEmpty()) return "batch:"+record.optString("albumBatch");
        String mime=record.optString("mime"); if (!mime.startsWith("image/")&&!"text/plain".equals(mime)) return "";
        Matcher file=FILE.matcher(record.optString("file"));
        return file.matches()?"legacy:"+record.optString("source")+"|"+record.optString("noteId")+"|"+file.group(1):"";
    }
    static int index(JSONObject record) {
        if (record.has("imageIndex")) return record.optInt("imageIndex");
        Matcher file=FILE.matcher(record.optString("file"));
        if (file.matches()&&!file.group(2).equals("正文")) return Integer.parseInt(file.group(2));
        return Integer.MAX_VALUE;
    }
    static JSONArray images(JSONObject album) {
        JSONArray result=new JSONArray(),items=album.optJSONArray("items");
        if (items!=null) for (int i=0;i<items.length();i++) { JSONObject item=items.optJSONObject(i); if (item!=null&&item.optString("mime").startsWith("image/")) result.put(item); }
        return result;
    }
    static JSONObject text(JSONObject album) {
        JSONArray items=album.optJSONArray("items"); if (items!=null) for (int i=0;i<items.length();i++) if ("text/plain".equals(items.optJSONObject(i).optString("mime"))) return items.optJSONObject(i);
        return null;
    }
    static JSONArray groups(JSONArray records) {
        JSONArray result=new JSONArray(); Map<String,List<JSONObject>> grouped=new LinkedHashMap<>(); Map<String,Integer> positions=new LinkedHashMap<>();
        for (int i=0;i<records.length();i++) {
            JSONObject record=records.optJSONObject(i); if (record==null) continue;
            String key=batch(record);
            if (key.isEmpty()) result.put(record);
            else {
                if (!grouped.containsKey(key)) { grouped.put(key,new ArrayList<>()); positions.put(key,result.length()); result.put(record); }
                grouped.get(key).add(record);
            }
        }
        for (String key:grouped.keySet()) try {
            List<JSONObject> list=grouped.get(key); list.sort(Comparator.comparingInt(AlbumRecords::index)); JSONObject first=null;
            for (JSONObject item:list) if (item.optString("mime").startsWith("image/")) { first=item; break; }
            if (first==null) continue; // A legacy standalone caption remains a normal text record.
            JSONObject album=new JSONObject().put("album",true).put("id",Long.MIN_VALUE+first.getLong("id"))
                .put("title",first.optString("albumTitle",SUFFIX.matcher(first.optString("title")).replaceFirst("")))
                .put("author",first.optString("author")).put("source",first.optString("source")).put("noteId",first.optString("noteId"))
                .put("description",first.optString("description")).put("time",first.optLong("time")).put("mime","image/album").put("items",new JSONArray(list));
            album.put("imageCount",images(album).length()); result.put(positions.get(key),album);
        } catch (Exception ignored) { }
        return result;
    }
}
