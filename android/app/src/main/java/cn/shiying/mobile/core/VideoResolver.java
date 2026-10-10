package cn.shiying.mobile.core;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.net.URLDecoder;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

public final class VideoResolver {
    public static final String MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1";
    public static final String ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36";
    public static final String DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
    private static final Pattern LINKS = Pattern.compile("https?://[^\\s<>\"'“”‘’，。！？；、（）【】]+", Pattern.CASE_INSENSITIVE);
    private static final Pattern ID = Pattern.compile("/(?:share/)?(?:video|note|slides)/(\\d+)");
    private static final Pattern SCRIPT = Pattern.compile("<script\\b([^>]*)>(.*?)</script>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern ROUTER = Pattern.compile("(?:window\\.)?(?:_ROUTER_DATA|_SSR_DATA|__INITIAL_STATE__|__INITIAL_SSR_STATE__|__APOLLO_STATE__|INIT_STATE|__INITIAL_DATA__|__NEXT_DATA__)\\s*=\\s*");

    public interface Cookies { String get(String url); default void save(String url,String value) { } }
    public interface Status { void show(String text); }
    private final Cookies cookies;
    private final Status status;
    private final CookieManager sessionCookies=new CookieManager(null,CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    public VideoResolver(Cookies cookies, Status status) { this.cookies = cookies; this.status = status; }

    public static class NeedsBrowser extends Exception {
        public final String url, id;
        public NeedsBrowser(String url, String id, String message) { super(message); this.url = url; this.id = id; }
    }

    public static String link(String text) throws Exception {
        Matcher m = LINKS.matcher(text == null ? "" : text.replace("https\\://","https://").replace("http\\://","http://"));
        Set<String> urls = new HashSet<>();
        String found = "";
        while (m.find()) {
            String s = m.group().replaceAll("[.,;!?)\\]})]+$", "");
            URI u = new URI(s);
            if (u.getHost() == null || u.getUserInfo() != null) throw new Exception("链接格式不正确，请使用完整分享链接。");
            int marker=s.indexOf('#');
            s=new URI(marker<0?s:s.substring(0,marker)).toASCIIString();
            urls.add(s); found = s;
        }
        if (urls.isEmpty()) throw new Exception("没有找到链接。可以直接粘贴整段抖音分享文字。");
        if (urls.size() > 1) throw new Exception("请一次添加一个视频链接。");
        if (found.startsWith("http://")&&Platforms.known(found)) found="https:"+found.substring(5);
        if (!found.startsWith("https://")) throw new Exception("请使用 https 链接，让连接保持安全。");
        return found;
    }

    public static boolean isDouyin(String url) {
        try {
            String host = new URI(url).getHost();
            if (host == null) return false;
            host = host.toLowerCase(Locale.ROOT);
            return host.equals("douyin.com") || host.endsWith(".douyin.com") || host.equals("iesdouyin.com") || host.endsWith(".iesdouyin.com");
        } catch (Exception e) { return false; }
    }

    public static String videoId(String url) {
        if (Xiaohongshu.supports(url)) return Xiaohongshu.id(url);
        String platformId=Platforms.id(url); if (!platformId.isEmpty()) return platformId;
        try {
            URI u = new URI(url);
            Matcher m = ID.matcher(u.getPath() == null ? "" : u.getPath());
            if (m.find()) return m.group(1);
            if (u.getRawQuery() != null) for (String pair : u.getRawQuery().split("&")) {
                String[] parts = pair.split("=", 2);
                if (parts.length == 2 && (parts[0].equals("modal_id") || parts[0].equals("aweme_id") || parts[0].equals("item_id"))) {
                    String value = URLDecoder.decode(parts[1], "UTF-8");
                    if (value.matches("\\d+")) return value;
                }
            }
        } catch (Exception ignored) { }
        return "";
    }

    public VideoInfo resolve(String text) throws Exception {
        String source = link(text);
        if (ChannelsService.supports(source)) {
            status.show("正在在线解析视频号链接…");
            return ChannelsService.resolve(this,source);
        }
        if (Xiaohongshu.supports(source)) return resolveXiaohongshu(source);
        if ("B站".equals(Platforms.name(source))) {
            try { return Bilibili.resolve(this,source); }
            catch (NeedsBrowser e) { throw e; }
            catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; throw new NeedsBrowser(source,videoId(source),"B站页面暂未响应，可在浏览器登录或验证后读取。"); }
        }
        if ("快手".equals(Platforms.name(source))||"视频号".equals(Platforms.name(source))) return resolveSocial(source);
        if (!isDouyin(source)) {
            String path = new URI(source).getPath().toLowerCase(Locale.ROOT);
            if (path.matches(".*\\.(?:jpg|jpeg|png|webp|gif|avif|heic)$")) {
                VideoInfo info=new VideoInfo(); info.sourceUrl=info.pageUrl=source; info.id=Long.toHexString(source.hashCode()&0xffffffffL); info.title=path.substring(path.lastIndexOf('/')+1); info.platform="图片直链";
                Albums.add(info,new JSONArray().put(source),info.platform); return info;
            }
            if (path.endsWith(".mp4") || path.endsWith(".webm") || path.endsWith(".mov")) {
                VideoInfo v = new VideoInfo();
                v.sourceUrl = v.pageUrl = source; v.id = Long.toHexString(source.hashCode() & 0xffffffffL);
                v.title = path.substring(path.lastIndexOf('/') + 1); v.formats.add(new VideoInfo.Format(source, "原始视频文件", 0, 0, 0));
                return v;
            }
            throw new NeedsBrowser(source, "", "这个网站需要在浏览器里播放视频后读取。");
        }
        status.show("正在展开分享链接…");
        Page page;
        try { page = fetch(source, ANDROID_UA, "", false); }
        catch (Exception e) {
            if (Thread.currentThread().isInterrupted()) throw e;
            if (e instanceof NeedsBrowser) throw e;
            throw new NeedsBrowser(source,videoId(source),"分享页暂时未响应，正在用浏览器读取目标视频。如需登录或验证，请手动完成。");
        }
        if (!isDouyin(page.url)) throw new Exception("分享链接未跳转到抖音，请检查链接。");
        String id = videoId(page.contentUrl);
        if (id.isEmpty()) id = videoId(page.url);
        if (id.isEmpty()) id = videoId(source);
        if (id.isEmpty()) throw new NeedsBrowser(page.url, "", "未找到单个视频编号，请在浏览器中打开目标视频。");
        String canonical = "https://www.douyin.com/video/" + id;
        VideoInfo info = fromHtml(page.body, id, source, canonical);
        if (info != null) { info.userAgent=ANDROID_UA; return info; }
        status.show("正在读取视频画质…");
        for (String candidate:new String[]{"https://www.iesdouyin.com/share/video/"+id+"/",canonical}) try {
            Page alternate=fetch(candidate,candidate.equals(canonical)?DESKTOP_UA:MOBILE_UA,"",false);
            info=fromHtml(alternate.body,id,source,canonical);
            if (info!=null) { info.userAgent=candidate.equals(canonical)?DESKTOP_UA:MOBILE_UA; return info; }
        } catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; }
        throw new NeedsBrowser(canonical, id, "分享页没有直接提供视频，可用浏览器完成登录或播放后解析。");
    }

    private VideoInfo resolveSocial(String source) throws Exception {
        String platform=Platforms.name(source); status.show("正在读取"+platform+"分享内容…"); String target=videoId(source),content=source;
        for (String agent:new String[]{DESKTOP_UA,ANDROID_UA}) try {
            Page page=fetch(source,agent,"",false); if (!Platforms.samePlatform(source,page.url)) throw new Exception("分享链接跳转到了其他网站。");
            content=page.contentUrl.isEmpty()?page.url:page.contentUrl; if (target.isEmpty()) target=videoId(content);
            VideoInfo info=fromHtml(page.body,target,source,content); if (info!=null) { info.userAgent=agent; return info; }
        } catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; }
        throw new NeedsBrowser(content,target,platform+"未提供可直接读取的完整内容，请在浏览器打开目标内容并完成登录或验证。视频号需有网页链接；微信卡片或受保护媒体不能直接解析。");
    }

    private VideoInfo resolveXiaohongshu(String source) throws Exception {
        status.show("正在读取小红书笔记…");
        Page page;
        try { page=fetch(source,DESKTOP_UA,"https://www.xiaohongshu.com/",false); }
        catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; throw new NeedsBrowser(source,Xiaohongshu.id(source),"小红书暂未提供笔记内容，请使用浏览器完成登录或验证后读取。"); }
        String target=Xiaohongshu.id(source); if (target.isEmpty()) target=Xiaohongshu.id(page.contentUrl);
        String content=page.contentUrl.isEmpty()?source:page.contentUrl;
        VideoInfo result=fromHtml(page.body,target,source,content);
        if (result!=null) return result;
        // A normal mobile share page may provide SSR data when the desktop page does not.
        if (!target.isEmpty()) try {
            Page mobile=fetch(content,MOBILE_UA,"https://www.xiaohongshu.com/",false);
            result=fromHtml(mobile.body,target,source,content); if (result!=null) return result;
        } catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; }
        throw new NeedsBrowser(content,target,"小红书要求登录或验证，或链接已过期。请在浏览器中打开目标笔记，手动完成后读取；不会把推荐内容当作目标笔记。");
    }

    public static VideoInfo fromHtml(String html, String target, String source, String page) {
        if ("B站".equals(Platforms.name(source))||"B站".equals(Platforms.name(page))) { VideoInfo info=Bilibili.fromHtml(html,target,source,page); if (info!=null) return info; }
        Matcher scripts = SCRIPT.matcher(html);
        while (scripts.find()) {
            String attrs = scripts.group(1), body = scripts.group(2);
            if (attrs.matches("(?is).*(RENDER_DATA|__NEXT_DATA__|SIGI_STATE|application/json).*")) {
                for (String candidate : new String[] {body, decode(body), entities(body)}) {
                    VideoInfo info = fromJsonText(candidate, target, source, page);
                    if (info != null) return info;
                }
            }
            Matcher router = ROUTER.matcher(body);
            while (router.find()) {
                VideoInfo info = fromJsonText(body.substring(router.end()), target, source, page);
                if (info != null) return info;
            }
        }
        return null;
    }

    public static VideoInfo fromJsonText(String text, String target, String source, String page) {
        try {
            String value=text.trim(); if (value.startsWith("JSON.parse(")) { Object parsed=new JSONTokener(value.substring(11)).nextValue(); if (parsed instanceof String) value=(String)parsed; }
            return fromPayload(new JSONTokener(normalizeState(value)).nextValue(), target, source, page);
        }
        catch (Exception ignored) { return null; }
    }

    public static VideoInfo fromPayload(Object payload, String target, String source, String page) {
        if (Xiaohongshu.supports(source)||Xiaohongshu.supports(page)) return Xiaohongshu.fromPayload(payload,target,source,page);
        String platform=Platforms.name(source); if (platform.isEmpty()) platform=Platforms.name(page);
        if ("B站".equals(platform)) return Bilibili.fromPayload(payload,target,source,page);
        if ("快手".equals(platform)||"视频号".equals(platform)) return SocialMedia.fromPayload(payload,target,source,page);
        if (target.isEmpty()&&(isDouyin(source)||isDouyin(page))) return null;
        ArrayDeque<Object> queue = new ArrayDeque<>();
        if (payload == null || payload == JSONObject.NULL) return null;
        queue.add(payload);
        int visited = 0;
        while (!queue.isEmpty() && visited++ < 60000) {
            Object node = queue.removeFirst();
            if (node instanceof JSONObject) {
                JSONObject o = (JSONObject) node;
                String id = first(o, "aweme_id", "awemeId", "id");
                JSONObject video = o.optJSONObject("video");
                if (!id.isEmpty() && (target.isEmpty() || target.equals(id))) {
                    JSONArray images=o.optJSONArray("images");
                    if (images!=null&&images.length()>0) {
                        VideoInfo v=photoItem(o,images,id,source,page); if (v!=null) return v;
                    } else if (video!=null) { VideoInfo v=item(o,video,id,source,page); if (!v.formats.isEmpty()) return v; }
                }
                Iterator<String> keys = o.keys();
                while (keys.hasNext()) {
                    Object value = o.opt(keys.next());
                    if (value instanceof JSONObject || value instanceof JSONArray) queue.addLast(value);
                }
            } else if (node instanceof JSONArray) {
                JSONArray a = (JSONArray) node;
                for (int i = 0; i < a.length(); i++) {
                    Object value = a.opt(i);
                    if (value instanceof JSONObject || value instanceof JSONArray) queue.addLast(value);
                }
            }
        }
        return null;
    }

    private static VideoInfo item(JSONObject o, JSONObject video, String id, String source, String page) {
        VideoInfo v = new VideoInfo();
        v.platform="抖音";
        v.id = id; v.sourceUrl = source; v.pageUrl = page; v.title = first(o, "desc", "description");
        if (v.title.isEmpty()) v.title = "抖音视频 " + id;
        JSONObject author = o.optJSONObject("author");
        if (author != null) v.author = author.optString("nickname");
        v.duration = video.optDouble("duration", 0) / 1000.0;
        List<String> covers = urls(object(video, "origin_cover", "cover"));
        if (!covers.isEmpty()) v.thumbnail = covers.get(0);
        Set<String> seen = new HashSet<>();
        JSONArray bitrates = array(video, "bit_rate", "bitRate", "bitrateInfo");
        if (bitrates != null) for (int i = 0; i < bitrates.length(); i++) {
            JSONObject b = bitrates.optJSONObject(i);
            if (b != null) add(v, object(b, "play_addr", "playAddr", "PlayAddr"), video,
                first(b, "gear_name", "gearName"), seen);
        }
        for (String key : new String[] {"play_addr_h264", "play_addr", "playAddr", "play_addr_bytevc1", "download_addr"})
            add(v, video.optJSONObject(key), video, key.equals("download_addr") ? "分享下载画质" : "播放画质", seen);
        Collections.sort(v.formats, (a, b) -> a.height == b.height ? Long.compare(b.size, a.size) : Integer.compare(b.height, a.height));
        return v;
    }
    private static VideoInfo photoItem(JSONObject object,JSONArray images,String id,String source,String page) {
        VideoInfo info=new VideoInfo(); info.id=id; info.platform="抖音"; info.sourceUrl=source; info.pageUrl=page; info.description=first(object,"desc","description"); info.title=info.description.isEmpty()?"抖音图文 "+id:info.description.split("\\n",2)[0];
        JSONObject author=object.optJSONObject("author"); if (author!=null) info.author=author.optString("nickname"); JSONArray pictures=new JSONArray();
        for (int i=0;i<images.length();i++) {
            JSONObject image=images.optJSONObject(i); if (image==null) return null;
            List<String> urls=urls(image); if (urls.isEmpty()) urls=urls(object(image,"display_image","origin_image")); if (urls.isEmpty()) return null;
            try { pictures.put(new JSONObject().put("url",urls.get(0)).put("width",image.optInt("width")).put("height",image.optInt("height"))); } catch (Exception e) { return null; }
        }
        return Albums.add(info,pictures,"抖音")?info:null;
    }

    private static void add(VideoInfo v, JSONObject addr, JSONObject video, String name, Set<String> seen) {
        if (addr == null || first(addr, "url_key", "UrlKey").contains("bytevc2")) return;
        List<String> list = urls(addr);
        if (list.isEmpty() || seen.contains(list.get(0))) return;
        seen.addAll(list);
        int width = addr.optInt("width", video.optInt("width")), height = addr.optInt("height", video.optInt("height"));
        String label = width > 0 && height > 0 ? width + " × " + height : (name.isEmpty() ? "可用画质" : name);
        VideoInfo.Format format=new VideoInfo.Format(list.get(0), label, width, height,
            addr.optLong("data_size", addr.optLong("dataSize", addr.optLong("DataSize"))));
        format.alternatives.addAll(list.subList(1,list.size())); v.formats.add(format);
    }

    private static List<String> urls(JSONObject o) {
        List<String> result = new ArrayList<>();
        if (o == null) return result;
        JSONArray a = array(o, "url_list", "urlList", "UrlList");
        if (a != null) for (int i = 0; i < a.length(); i++) {
            String s = mediaUrl(a.optString(i));
            if (!s.isEmpty() && !result.contains(s)) result.add(s);
        }
        return result;
    }
    private static JSONObject object(JSONObject o, String... keys) { for (String k : keys) if (o.optJSONObject(k) != null) return o.optJSONObject(k); return null; }
    private static JSONArray array(JSONObject o, String... keys) { for (String k : keys) if (o.optJSONArray(k) != null) return o.optJSONArray(k); return null; }
    private static String first(JSONObject o, String... keys) { for (String k : keys) { String v = o.optString(k); if (!v.isEmpty() && !v.equals("null")) return v; } return ""; }
    public static String mediaUrl(String raw) {
        if (raw==null) return "";
        String url=raw.startsWith("//")?"https:"+raw:raw;
        try {
            URI u=new URI(url); String host=u.getHost(); if (host==null||u.getUserInfo()!=null) return "";
            if ("http".equalsIgnoreCase(u.getScheme())) {
                String h=host.toLowerCase(Locale.ROOT); boolean official=isDouyin(url);
                for (String domain:new String[]{"douyinvod.com","douyinpic.com","bytecdn.cn","bytecdn.com","bytedance.net","bytedance.com"})
                    if (h.equals(domain)||h.endsWith("."+domain)) official=true;
                if (!official) return ""; url="https:"+url.substring(5);
            }
            return url.startsWith("https://")?url:"";
        } catch (Exception e) { return ""; }
    }
    private static String decode(String s) { try { return URLDecoder.decode(s.replace("+", "%2B"), "UTF-8"); } catch (Exception e) { return s; } }
    private static String entities(String s) { return s.replace("&quot;", "\"").replace("&#34;", "\"").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"); }

    static String normalizeState(String s) {
        StringBuilder out=new StringBuilder(s.length()); char quote=0; boolean escaped=false;
        for (int i=0;i<s.length();) {
            char c=s.charAt(i);
            if (quote!=0) { out.append(c); i++; if (escaped) escaped=false; else if (c=='\\') escaped=true; else if (c==quote) quote=0; continue; }
            if (c=='\"'||c=='\'') { quote=c; out.append(c); i++; continue; }
            if (Character.isJavaIdentifierStart(c)) {
                int end=i+1; while (end<s.length()&&Character.isJavaIdentifierPart(s.charAt(end))) end++;
                String word=s.substring(i,end); out.append(word.equals("undefined")||word.equals("NaN")?"null":word); i=end;
            } else { out.append(c); i++; }
        }
        return out.toString();
    }

    public static final class Page { public String url, body, mime, ext,contentUrl=""; public long size; public byte[] head; }

    /** A link-only service request intentionally omits all user cookies and account headers. */
    public JSONObject postJson(String endpoint,JSONObject body,String referer) throws Exception {
        if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
        URI uri=new URI(endpoint);
        if (!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null) throw new Exception("解析服务地址无效。");
        HttpURLConnection connection=(HttpURLConnection)new URL(endpoint).openConnection();
        connection.setRequestMethod("POST"); connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(12000); connection.setReadTimeout(22000); connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type","application/json; charset=utf-8"); connection.setRequestProperty("Accept","application/json"); connection.setRequestProperty("User-Agent",DESKTOP_UA); connection.setRequestProperty("Referer",referer);
        byte[] payload=body.toString().getBytes(StandardCharsets.UTF_8); connection.setFixedLengthStreamingMode(payload.length);
        try {
            try (java.io.OutputStream output=connection.getOutputStream()) { output.write(payload); }
            int code=connection.getResponseCode();
            if (code==429) throw new Exception("视频号解析请求过于频繁，请稍后重试。");
            if (code<200||code>=300) throw new Exception("视频号在线解析服务暂不可用（"+code+"），请稍后重试。");
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try (InputStream input=connection.getInputStream()) {
                byte[] buffer=new byte[8192]; int n;
                while ((n=input.read(buffer))>0) { if (Thread.currentThread().isInterrupted()) throw new InterruptedException(); if (bytes.size()+n>2*1024*1024) throw new Exception("解析响应过大。"); bytes.write(buffer,0,n); }
            }
            try { return new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8)); }
            catch (Exception e) { throw new Exception("解析服务返回的数据无效，请稍后重试。"); }
        } catch (java.net.SocketTimeoutException e) { throw new Exception("视频号在线解析超时，请稍后重试。"); }
        finally { connection.disconnect(); }
    }

    public Page fetch(String source, String ua, String referer, boolean probe) throws Exception {
        return fetch(source,ua,referer,probe,"video");
    }
    public Page fetch(String source, String ua, String referer, boolean probe,String expectedKind) throws Exception {
        String current = source;
        String contentUrl=videoId(source).isEmpty()?"":source;
        for (int redirect = 0; redirect < 9; redirect++) {
            if (Thread.currentThread().isInterrupted()) throw new Exception("任务已取消。");
            URI uri = new URI(current);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null)
                throw new Exception("只支持安全的 https 视频地址。");
            HttpURLConnection connection = (HttpURLConnection) new URL(current).openConnection();
            connection.setConnectTimeout(12000); connection.setReadTimeout(18000); connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("User-Agent", ua); connection.setRequestProperty("Accept-Encoding", "identity");
            if (!referer.isEmpty()) connection.setRequestProperty("Referer", referer);
            String cookie = cookies.get(current);
            java.util.LinkedHashMap<String,String> merged=new java.util.LinkedHashMap<>();
            if (cookie!=null) mergeCookies(merged,cookie);
            for (String session:sessionCookies.get(uri,java.util.Collections.emptyMap()).getOrDefault("Cookie",java.util.Collections.emptyList())) mergeCookies(merged,session);
            if (!merged.isEmpty()) {
                StringBuilder value=new StringBuilder();
                for (java.util.Map.Entry<String,String> entry:merged.entrySet()) { if (value.length()>0) value.append("; "); value.append(entry.getKey()).append('=').append(entry.getValue()); }
                connection.setRequestProperty("Cookie",value.toString());
            }
            if (probe) connection.setRequestProperty("Range", "bytes=0-1023");
            try {
                int status = connection.getResponseCode();
                sessionCookies.put(uri,connection.getHeaderFields());
                for (java.util.Map.Entry<String,List<String>> header:connection.getHeaderFields().entrySet())
                    if (header.getKey()!=null&&header.getKey().equalsIgnoreCase("Set-Cookie"))
                        for (String value:header.getValue()) cookies.save(current,value);
                if (status >= 300 && status < 400) {
                    String location = connection.getHeaderField("Location");
                    if (location == null) throw new Exception("分享页跳转地址缺失。");
                    current = new URL(new URL(current), location).toString();
                    if (Platforms.known(current)&&!videoId(current).isEmpty()) contentUrl=current;
                    continue;
                }
                if (status != 200 && status != 206) {
                    if (!probe&&isDouyin(contentUrl)) throw new NeedsBrowser(contentUrl,videoId(contentUrl),"分享页暂时返回 "+status+"，可用浏览器读取目标视频。");
                    throw new Exception("服务器返回 " + status + "。可重新解析或使用浏览器辅助。");
                }
                Page page = new Page(); page.url = current; page.contentUrl=contentUrl; page.mime = connection.getContentType();
                String length = connection.getHeaderField("Content-Length");
                page.size = length == null ? 0 : Long.parseLong(length);
                int limit = probe ? 1024 : 5 * 1024 * 1024;
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                InputStream raw=connection.getInputStream();
                if ("gzip".equalsIgnoreCase(connection.getContentEncoding())) raw=new java.util.zip.GZIPInputStream(raw);
                try (InputStream input = raw) {
                    byte[] chunk = new byte[8192];
                    int n;
                    while ((n = input.read(chunk, 0, Math.min(chunk.length, limit - bytes.size()))) > 0) {
                        if (Thread.currentThread().isInterrupted()) throw new Exception("任务已取消。");
                        bytes.write(chunk, 0, n);
                        if (bytes.size() == limit) break;
                    }
                }
                byte[] body = bytes.toByteArray();
                if (!probe && bytes.size() == limit) throw new Exception("分享页数据过大，请使用浏览器辅助解析。");
                if (probe) {
                    if ("encoded".equals(expectedKind)) { page.head=body; page.ext="bin"; page.mime="application/octet-stream"; return page; }
                    MediaHeaders.Type type=MediaHeaders.detect(body,body.length,"audio".equals(expectedKind)?"video":expectedKind);
                    if (type==null) throw new Exception("收到的不是预期的"+("image".equals(expectedKind)?"图片":"视频")+"文件。请刷新链接或使用浏览器辅助解析。");
                    page.ext="audio".equals(expectedKind)?"m4a":type.ext; page.mime="audio".equals(expectedKind)?"audio/mp4":type.mime;
                } else page.body = new String(body, StandardCharsets.UTF_8);
                return page;
            } finally { connection.disconnect(); }
        }
        throw new Exception("链接跳转次数过多，请复制目标视频的完整网页地址。");
    }

    public Page probe(VideoInfo info, VideoInfo.Format format) throws Exception {
        VideoInfo.Asset asset=new VideoInfo.Asset(format.url,info.isImages()?"image":"video",1);
        asset.alternatives.addAll(format.alternatives); return probe(info,asset);
    }
    public Page probe(VideoInfo info,VideoInfo.Asset asset) throws Exception {
        status.show("正在确认"+("image".equals(asset.kind)?"图片":"视频")+"文件…");
        List<String> urls=new ArrayList<>(); urls.add(asset.url); urls.addAll(asset.alternatives); Exception failure=null;
        for (String url:urls) try {
            Page page=fetch(url,info.userAgent,referer(info),true,asset.decodeKey.isEmpty()?asset.kind:"encoded");
            if (!asset.decodeKey.isEmpty()) {
                byte[] clear=page.head.clone(); new ChannelsCodec(asset.decodeKey).apply(clear,0,clear.length);
                if (MediaHeaders.detect(clear,clear.length,"video")==null) throw new Exception("网页播放参数与媒体不匹配，请重新读取目标视频。");
            }
            return page;
        }
        catch (Exception e) { if (Thread.currentThread().isInterrupted()) throw e; failure=e; }
        throw failure==null?new Exception("没有可用的媒体地址。"):failure;
    }
    public static String referer(VideoInfo info) {
        String platform=Platforms.name(info.sourceUrl);
        return "小红书".equals(platform)?"https://www.xiaohongshu.com/":"B站".equals(platform)?"https://www.bilibili.com/":"快手".equals(platform)?"https://www.kuaishou.com/":"视频号".equals(platform)?"https://channels.weixin.qq.com/":info.pageUrl;
    }

    private static void mergeCookies(java.util.Map<String,String> jar,String header) {
        for (String entry:header.split(";")) { int split=entry.indexOf('='); if (split>0) { String key=entry.substring(0,split).trim(); if (!key.startsWith("$")) jar.put(key,entry.substring(split+1).trim()); } }
    }

    public static String filename(String title, String id) {
        String text = title.replaceAll("[<>:\"/\\\\|?*\\p{Cntrl}]", "_").trim();
        if (text.codePointCount(0,text.length()) > 56) text=text.substring(0,text.offsetByCodePoints(0,56));
        if (text.isEmpty()) text = "视频";
        return text + " [" + id.replaceAll("[^a-zA-Z0-9_-]", "") + "]";
    }
}
