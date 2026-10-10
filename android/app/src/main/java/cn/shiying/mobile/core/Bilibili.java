package cn.shiying.mobile.core;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.HashSet;
import java.util.Set;

/** Read regular Bilibili view/playback/dynamic data; paid or DRM sources are not synthesized. */
public final class Bilibili {
    private static final String ROOT="https://www.bilibili.com/";
    public static VideoInfo resolve(VideoResolver resolver,String source) throws Exception {
        String id=Platforms.id(source),page=source;
        if (id.isEmpty()) { VideoResolver.Page expanded=resolver.fetch(source,VideoResolver.DESKTOP_UA,ROOT,false); page=expanded.contentUrl.isEmpty()?expanded.url:expanded.contentUrl; id=Platforms.id(page); }
        if (id.isEmpty()) throw new VideoResolver.NeedsBrowser(page,"","未识别到 B站的单个视频或图文编号，请打开目标内容后读取。");
        if (id.startsWith("opus")) {
            JSONObject payload=json(resolver,"https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?id="+id.substring(4));
            VideoInfo album=fromPayload(payload,id,source,page); if (album!=null) return album;
            throw new VideoResolver.NeedsBrowser(page,id,"B站动态尚未提供完整图文，请登录后打开原动态。");
        }
        if (id.startsWith("cv")) {
            VideoResolver.Page article=resolver.fetch(page,VideoResolver.DESKTOP_UA,ROOT,false); VideoInfo pictures=article(article.body,id,source,page);
            if (pictures!=null) return pictures; throw new VideoResolver.NeedsBrowser(page,id,"请在浏览器打开 B站专栏正文后读取图片。");
        }
        JSONObject view=json(resolver,"https://api.bilibili.com/x/web-interface/view?"+(id.startsWith("av")?"aid="+id.substring(2):"bvid="+id));
        JSONObject meta=view.optJSONObject("data"); if (view.optInt("code",-1)!=0||meta==null||!matches(meta,id)) throw new VideoResolver.NeedsBrowser(page,id,"B站要求登录、验证，或内容不可访问，请在浏览器打开目标视频。");
        String bvid=meta.optString("bvid"),canonical=ROOT+"video/"+bvid;
        String p=Platforms.query(source,"p"); if (p.isEmpty()) p=Platforms.query(page,"p"); int index=1; try { index=Math.max(1,Integer.parseInt(p)); } catch (Exception ignored) { }
        JSONArray pages=meta.optJSONArray("pages");
        if (pages==null||index>pages.length()) throw new Exception("所选 B站分 P 不存在。");
        JSONObject part=pages.optJSONObject(index-1); if (part==null) throw new Exception("未找到所选分 P 的播放信息。");
        String cid=part.optString("cid"); canonical+="?p="+index;
        VideoInfo info=metadata(meta,source,canonical); if (pages.length()>1) info.title+=" · P"+index+" "+part.optString("part");
        info.duration=part.optDouble("duration",meta.optDouble("duration",0));
        String api="https://api.bilibili.com/x/player/playurl?bvid="+bvid+"&cid="+cid;
        try { play(info,json(resolver,api+"&qn=64&fnval=16&fnver=0&fourk=0").optJSONObject("data")); } catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; }
        try { play(info,json(resolver,api+"&qn=32&fnval=1&platform=html5").optJSONObject("data")); } catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; }
        if (info.formats.isEmpty()) throw new VideoResolver.NeedsBrowser(canonical,bvid,"B站未提供可访问的完整媒体，请登录后重新读取；不会将预览片段当作完整视频。");
        return info;
    }
    private static JSONObject json(VideoResolver resolver,String url) throws Exception { return new JSONObject(resolver.fetch(url,VideoResolver.DESKTOP_UA,ROOT,false).body); }
    private static boolean matches(JSONObject object,String target) { return target.equals(object.optString("bvid"))||target.equals("av"+object.optString("aid")); }
    private static VideoInfo metadata(JSONObject meta,String source,String page) {
        VideoInfo info=new VideoInfo(); info.id=meta.optString("bvid"); info.platform="B站"; info.sourceUrl=source; info.pageUrl=page;
        info.title=meta.optString("title","B站视频 "+info.id); info.description=meta.optString("desc"); info.thumbnail=Platforms.media(meta.optString("pic"),"B站"); info.duration=meta.optDouble("duration",0);
        JSONObject owner=meta.optJSONObject("owner"); if (owner!=null) info.author=owner.optString("name"); return info;
    }
    public static void play(VideoInfo info,JSONObject data) {
        if (data==null||data.optBoolean("is_preview")||data.optInt("is_preview")==1||data.optBoolean("is_drm")||data.optInt("drm_tech_type")!=0) return;
        Set<String> seen=new HashSet<>(); for (VideoInfo.Format f:info.formats) seen.add(f.url);
        JSONObject dash=data.optJSONObject("dash");
        if (dash!=null) {
            JSONArray audio=dash.optJSONArray("audio"),video=dash.optJSONArray("video"); JSONObject chosen=null;
            if (audio!=null) for (int i=0;i<audio.length();i++) { JSONObject a=audio.optJSONObject(i); if (a!=null&&a.optString("codecs").startsWith("mp4a")&&(chosen==null||a.optLong("bandwidth")>chosen.optLong("bandwidth"))) chosen=a; }
            if (chosen!=null&&video!=null) for (int i=0;i<video.length();i++) {
                JSONObject v=video.optJSONObject(i); if (v==null||!v.optString("codecs").startsWith("avc1")||v.optBoolean("drm")) continue;
                VideoInfo.Asset picture=stream(v,"video",1),sound=stream(chosen,"audio",2); if (picture==null||sound==null||!seen.add(picture.url)) continue;
                VideoInfo.Format format=new VideoInfo.Format(picture.url,v.optInt("width")+" × "+v.optInt("height")+" · 含声音",v.optInt("width"),v.optInt("height"),0);
                format.mode="dash"; format.assets.add(picture); format.assets.add(sound); info.formats.add(format);
            }
        }
        JSONArray durl=data.optJSONArray("durl");
        if (durl!=null&&durl.length()>0&&!data.optString("format").startsWith("flv")) {
            VideoInfo.Format direct=null; long size=0; boolean valid=true;
            for (int i=0;i<durl.length();i++) {
                JSONObject item=durl.optJSONObject(i); if (item==null) { valid=false; break; }
                String url=Platforms.media(item.optString("url"),"B站"); if (url.isEmpty()) { valid=false; break; }
                if (direct==null) direct=new VideoInfo.Format(url,"完整 MP4 · 含声音",0,qualityHeight(data.optInt("quality")),0);
                VideoInfo.Asset asset=new VideoInfo.Asset(url,"video",i+1); backups(asset,item.optJSONArray("backup_url")); direct.assets.add(asset); size+=item.optLong("size");
            }
            if (valid&&direct!=null&&seen.add(direct.url)) {
                direct.size=size;
                if (durl.length()==1) { direct.alternatives.addAll(direct.assets.get(0).alternatives); direct.assets.clear(); }
                else direct.mode="concat";
                info.formats.add(direct);
            }
        }
        info.formats.sort((a,b)->Integer.compare(b.height,a.height));
    }
    private static int qualityHeight(int quality) { return quality>=80?1080:quality>=64?720:quality>=32?480:360; }
    private static VideoInfo.Asset stream(JSONObject item,String kind,int index) {
        String url=Platforms.media(item.optString("baseUrl",item.optString("base_url")),"B站"); if (url.isEmpty()) return null;
        VideoInfo.Asset asset=new VideoInfo.Asset(url,kind,index); backups(asset,item.optJSONArray("backupUrl")!=null?item.optJSONArray("backupUrl"):item.optJSONArray("backup_url")); return asset;
    }
    private static void backups(VideoInfo.Asset asset,JSONArray values) { if (values!=null) for (int i=0;i<values.length();i++) { String url=Platforms.media(values.optString(i),"B站"); if (!url.isEmpty()&&!asset.alternatives.contains(url)) asset.alternatives.add(url); } }
    public static VideoInfo fromPayload(Object payload,String target,String source,String page) {
        if (target.isEmpty()) return null;
        if (target.startsWith("cv")&&payload instanceof JSONObject) {
            JSONObject value=(JSONObject)payload; String html=value.optString("articleHtml"); if (!html.isEmpty()) { VideoInfo info=article(html,target,source,page); if (info!=null&&!value.optString("articleTitle").isEmpty()) info.title=value.optString("articleTitle"); return info; }
        }
        ArrayDeque<Object> queue=new ArrayDeque<>(); if (payload!=null&&payload!=JSONObject.NULL) queue.add(payload); int count=0;
        while (!queue.isEmpty()&&count++<60000) {
            Object node=queue.removeFirst();
            if (node instanceof JSONObject) {
                JSONObject o=(JSONObject)node;
                if (target.startsWith("opus")&&target.substring(4).equals(o.optString("id_str",o.optString("id")))) {
                    VideoInfo album=dynamic(o,target,source,page); if (album!=null) return album;
                }
                if (matches(o,target)&&o.has("title")) {
                    VideoInfo info=metadata(o,source,page); JSONObject play=boundPlay(payload,o,source,page); play(info,play); if (!info.formats.isEmpty()) return info;
                }
                Iterator<String> keys=o.keys(); while (keys.hasNext()) { Object child=o.opt(keys.next()); if (child instanceof JSONObject||child instanceof JSONArray) queue.add(child); }
            } else if (node instanceof JSONArray) for (int i=0;i<((JSONArray)node).length();i++) { Object child=((JSONArray)node).opt(i); if (child instanceof JSONObject||child instanceof JSONArray) queue.add(child); }
        }
        return null;
    }
    private static JSONObject boundPlay(Object payload,JSONObject meta,String source,String page) {
        if (!(payload instanceof JSONObject)) return null; JSONObject root=(JSONObject)payload;
        String context=root.optString("biliPage"); if (!Platforms.samePlatform(page,context)||!meta.optString("bvid").equals(Platforms.id(context))) return null;
        String request=root.optString("requestUrl");
        if (!request.isEmpty()) {
            if (!Platforms.host(request,"api.bilibili.com")||!meta.optString("bvid").equals(Platforms.query(request,"bvid"))) return null;
            int part=1; try { part=Math.max(1,Integer.parseInt(Platforms.query(context,"p"))); } catch (Exception ignored) { }
            JSONArray pages=meta.optJSONArray("pages"); if (pages==null||part>pages.length()||pages.optJSONObject(part-1)==null||!pages.optJSONObject(part-1).optString("cid").equals(Platforms.query(request,"cid"))) return null;
        }
        JSONObject data=root.optJSONObject("playInfo"); if (data==null||data.optInt("code",0)!=0) return null;
        return data.optJSONObject("data")!=null?data.optJSONObject("data"):data;
    }
    public static VideoInfo fromHtml(String html,String target,String source,String page) {
        if (target.startsWith("cv")) return article(html,target,source,page);
        JSONObject metadata=null,play=null;
        java.util.regex.Matcher scripts=java.util.regex.Pattern.compile("<script\\b[^>]*>(.*?)</script>",java.util.regex.Pattern.CASE_INSENSITIVE|java.util.regex.Pattern.DOTALL).matcher(html);
        while (scripts.find()) {
            String body=scripts.group(1); java.util.regex.Matcher marker=java.util.regex.Pattern.compile("(?:window\\.)?(__INITIAL_STATE__|__playinfo__)\\s*=\\s*").matcher(body);
            while (marker.find()) try {
                Object parsed=new org.json.JSONTokener(VideoResolver.normalizeState(body.substring(marker.end()).trim())).nextValue();
                if (parsed instanceof JSONObject) { if (marker.group(1).equals("__playinfo__")) play=(JSONObject)parsed; else metadata=(JSONObject)parsed; }
            } catch (Exception ignored) { }
        }
        if (metadata==null||play==null) return null;
        try { return fromPayload(new JSONObject().put("biliPage",page).put("metadata",metadata).put("playInfo",play),target,source,page); }
        catch (Exception e) { return null; }
    }
    private static VideoInfo article(String html,String target,String source,String page) {
        if (!target.equals(Platforms.id(page))) return null;
        int start=html.indexOf("article-holder"); if (start<0) return null;
        String body=html.substring(start); int end=body.indexOf("article-footer"); if (end>=0) body=body.substring(0,end);
        JSONArray images=new JSONArray(); Set<String> seen=new HashSet<>();
        java.util.regex.Matcher figures=java.util.regex.Pattern.compile("<figure\\b[^>]*>(.*?)</figure>",java.util.regex.Pattern.CASE_INSENSITIVE|java.util.regex.Pattern.DOTALL).matcher(body);
        while (figures.find()) {
            java.util.regex.Matcher image=java.util.regex.Pattern.compile("<img\\b([^>]*)>",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(figures.group(1));
            if (!image.find()) continue; String attrs=image.group(1);
            java.util.regex.Matcher urlMatch=java.util.regex.Pattern.compile("data-src=[\"']([^\"']+)[\"']",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(attrs);
            if (!urlMatch.find()) { urlMatch=java.util.regex.Pattern.compile("(?:^|\\s)src=[\"']([^\"']+)[\"']",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(attrs); if (!urlMatch.find()) continue; }
            String url=Platforms.media(urlMatch.group(1).replace("&amp;","&"),"B站"); if (!url.isEmpty()&&seen.add(url)) images.put(url);
        }
        VideoInfo info=new VideoInfo(); info.id=target; info.platform="B站"; info.sourceUrl=source; info.pageUrl=page; info.title="B站专栏 "+target;
        java.util.regex.Matcher title=java.util.regex.Pattern.compile("<title>(.*?)</title>",java.util.regex.Pattern.CASE_INSENSITIVE|java.util.regex.Pattern.DOTALL).matcher(html); if (title.find()) info.title=title.group(1).replace(" - 哔哩哔哩","").trim();
        return Albums.add(info,images,"B站")?info:null;
    }
    private static VideoInfo dynamic(JSONObject object,String target,String source,String page) {
        JSONObject modules=object.optJSONObject("modules"),dynamic=modules==null?null:modules.optJSONObject("module_dynamic"),major=dynamic==null?null:dynamic.optJSONObject("major");
        if (major==null) return null; JSONObject draw=major.optJSONObject("draw"),opus=major.optJSONObject("opus");
        JSONArray images=draw==null?null:draw.optJSONArray("items"); if (images==null&&opus!=null) images=opus.optJSONArray("pics");
        VideoInfo info=new VideoInfo(); info.id=target; info.platform="B站"; info.sourceUrl=source; info.pageUrl=page;
        JSONObject desc=dynamic.optJSONObject("desc"),author=modules.optJSONObject("module_author"); info.description=desc==null?"":desc.optString("text");
        if (info.description.isEmpty()&&opus!=null&&opus.optJSONObject("summary")!=null) info.description=opus.optJSONObject("summary").optString("text");
        info.title=opus==null?"B站图文 "+target:opus.optString("title","B站图文 "+target); if (author!=null) info.author=author.optString("name");
        return Albums.add(info,images,"B站")?info:null;
    }
}
