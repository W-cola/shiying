package cn.shiying.mobile.core;

import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URI;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Read the target note's published state, preserving its provided media URLs. */
public final class Xiaohongshu {
    private static final Pattern NOTE=Pattern.compile("/(?:explore|discovery/item)/([a-fA-F0-9]{24})(?:/|$)");
    public static boolean supports(String url) { return host(url,"xiaohongshu.com")||host(url,"xhslink.com"); }
    private static boolean host(String url,String domain) {
        try { String host=new URI(url).getHost(); return host!=null&&(host.equalsIgnoreCase(domain)||host.toLowerCase(Locale.ROOT).endsWith("."+domain)); }
        catch (Exception e) { return false; }
    }
    public static String id(String url) {
        try { Matcher m=NOTE.matcher(new URI(url).getPath()); return m.find()?m.group(1).toLowerCase(Locale.ROOT):""; }
        catch (Exception e) { return ""; }
    }
    public static String mediaUrl(String raw) {
        if (raw==null||raw.isEmpty()) return "";
        String url=raw.startsWith("//")?"https:"+raw:raw;
        if (url.startsWith("http://")&&(host(url,"xhscdn.com")||host(url,"xhscdn.net")||host(url,"xiaohongshu.com"))) url="https:"+url.substring(5);
        try { URI u=new URI(url); return "https".equalsIgnoreCase(u.getScheme())&&u.getHost()!=null&&u.getUserInfo()==null?url:""; }
        catch (Exception e) { return ""; }
    }
    public static VideoInfo fromPayload(Object payload,String target,String source,String page) {
        if (target.isEmpty()) return null;
        ArrayDeque<Object> todo=new ArrayDeque<>(); if (payload instanceof JSONObject||payload instanceof JSONArray) todo.add(payload);
        int visited=0;
        while (!todo.isEmpty()&&visited++<60000) {
            Object value=todo.removeFirst();
            if (value instanceof JSONObject) {
                JSONObject o=(JSONObject)value;
                String id=o.optString("noteId",o.optString("note_id",o.optString("id")));
                if (target.equalsIgnoreCase(id)&&(!o.optString("type").isEmpty()||o.has("imageList")||o.has("video"))) {
                    VideoInfo result=note(o,target,source,page); if (result!=null) return result;
                }
                Iterator<String> keys=o.keys(); while (keys.hasNext()) { Object child=o.opt(keys.next()); if (child instanceof JSONObject||child instanceof JSONArray) todo.addLast(child); }
            } else {
                JSONArray list=(JSONArray)value;
                for (int i=0;i<list.length();i++) { Object child=list.opt(i); if (child instanceof JSONObject||child instanceof JSONArray) todo.addLast(child); }
            }
        }
        return null;
    }
    private static VideoInfo note(JSONObject note,String id,String source,String page) {
        VideoInfo v=new VideoInfo(); v.id=id; v.sourceUrl=source; v.pageUrl=page; v.platform="小红书";
        v.description=note.optString("desc"); v.title=note.optString("title");
        if (v.title.isEmpty()) v.title=v.description.isEmpty()?"小红书笔记 "+id:v.description.split("\\n",2)[0];
        JSONObject user=note.optJSONObject("user"); if (user!=null) v.author=user.optString("nickname",user.optString("nickName"));
        JSONArray images=note.optJSONArray("imageList");
        if (images!=null&&images.length()>0&&images.optJSONObject(0)!=null) v.thumbnail=imageUrl(images.optJSONObject(0));
        String type=note.optString("type"); JSONObject video=note.optJSONObject("video");
        if ("video".equalsIgnoreCase(type)||video!=null&&video.length()>0&&!"normal".equalsIgnoreCase(type)&&!"image".equalsIgnoreCase(type)) {
            if (video==null) return null;
            JSONObject media=video.optJSONObject("media"), stream=media==null?null:media.optJSONObject("stream");
            Set<String> seen=new HashSet<>();
            if (stream!=null) {
                Iterator<String> codecs=stream.keys();
                while (codecs.hasNext()) { JSONArray formats=stream.optJSONArray(codecs.next()); if (formats==null) continue;
                    for (int i=0;i<formats.length();i++) { JSONObject format=formats.optJSONObject(i); if (format==null||format.optBoolean("hasDrm")||format.optBoolean("drm")) continue;
                        String url=mediaUrl(format.optString("masterUrl")); JSONArray backups=format.optJSONArray("backupUrls");
                        if (url.isEmpty()&&backups!=null) for (int j=0;j<backups.length()&&url.isEmpty();j++) url=mediaUrl(backups.optString(j));
                        if (url.isEmpty()||!seen.add(url)||url.toLowerCase(Locale.ROOT).contains(".m3u8")) continue;
                        int w=format.optInt("width"),h=format.optInt("height");
                        String label=w>0&&h>0?w+" × "+h:format.optString("qualityType","播放画质");
                        v.formats.add(new VideoInfo.Format(url,label,w,h,format.optLong("size")));
                        if (v.duration==0) v.duration=format.optDouble("duration",0)/1000.0;
                    }
                }
            }
            // Only use URLs actually supplied by the note; never construct a guessed origin-video URL.
            for (String key:new String[]{"url","playUrl","masterUrl"}) { String url=mediaUrl(video.optString(key)); if (!url.isEmpty()&&seen.add(url)) v.formats.add(new VideoInfo.Format(url,"播放画质",0,0,0)); }
            v.formats.sort((a,b)->a.height==b.height?Long.compare(b.size,a.size):Integer.compare(b.height,a.height));
            return v.formats.isEmpty()?null:v;
        }
        if (images==null||images.length()==0) return null;
        v.kind="images"; VideoInfo.Format all=new VideoInfo.Format("","全部图片",0,0,0);
        for (int i=0;i<images.length();i++) {
            JSONObject image=images.optJSONObject(i); if (image==null) return null;
            String url=imageUrl(image); if (url.isEmpty()) return null; // don't silently produce an incomplete album
            int w=image.optInt("width"),h=image.optInt("height");
            VideoInfo.Asset asset=new VideoInfo.Asset(url,"image",i+1); all.assets.add(asset);
            VideoInfo.Format single=new VideoInfo.Format(url,"第 "+(i+1)+" 张"+(w>0&&h>0?" · "+w+" × "+h:""),w,h,0);
            single.assets.add(asset); v.formats.add(single);
        }
        if (all.assets.isEmpty()) return null;
        all.url=all.assets.get(0).url; all.label="全部图片 · "+all.assets.size()+" 张"; v.formats.add(0,all);
        return v;
    }
    private static String imageUrl(JSONObject image) {
        JSONArray variants=image.optJSONArray("infoList"); String main="";
        if (variants!=null) for (int i=0;i<variants.length();i++) { JSONObject o=variants.optJSONObject(i); if (o!=null&&"WB_DFT".equals(o.optString("imageScene"))) { main=mediaUrl(o.optString("url")); if (!main.isEmpty()) break; } }
        if (main.isEmpty()) main=mediaUrl(image.optString("urlDefault"));
        if (main.isEmpty()) main=mediaUrl(image.optString("url"));
        if (main.isEmpty()) main=mediaUrl(image.optString("urlPre"));
        return main;
    }
    public static String textDocument(VideoInfo v) {
        String source=v.pageUrl;
        try { URI u=new URI(source); source=new URI(u.getScheme(),u.getAuthority(),u.getPath(),null,null).toString(); } catch (Exception ignored) { }
        return v.title+"\n\n作者："+v.author+"\n平台：小红书\n笔记编号："+v.id+"\n来源："+source+"\n\n"+v.description+"\n";
    }
}
