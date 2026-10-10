package cn.shiying.mobile.core;

import org.json.JSONObject;
import java.net.URI;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Public link-only API: no user account, cookies, private app data or device identifiers. */
public final class ChannelsService {
    public static final String ENDPOINT="https://v.mtotech.com/api/resolve";
    public static String shareId(String source) {
        try {
            URI uri=new URI(source); if (!"https".equalsIgnoreCase(uri.getScheme())||!"weixin.qq.com".equalsIgnoreCase(uri.getHost())||uri.getUserInfo()!=null) return "";
            Matcher matcher=Pattern.compile("^/sph/([A-Za-z0-9]{1,128})/?$").matcher(uri.getPath()); return matcher.matches()?matcher.group(1):"";
        } catch (Exception e) { return ""; }
    }
    public static boolean supports(String source) { return !shareId(source).isEmpty(); }
    public static VideoInfo resolve(VideoResolver resolver,String source) throws Exception {
        if (!supports(source)) throw new Exception("请使用完整的视频号分享链接。");
        JSONObject response=resolver.postJson(ENDPOINT,new JSONObject().put("url",source),"https://v.mtotech.com/");
        VideoInfo info=fromResponse(response,source);
        if (info==null) throw new Exception("解析服务未返回完整视频。请重新复制链接，或稍后重试。");
        return info;
    }
    public static VideoInfo fromResponse(JSONObject response,String source) {
        String id=shareId(source); JSONObject data=response.optJSONObject("data");
        if (id.isEmpty()||!response.optBoolean("ok")||data==null||data.optInt("media_type",4)!=4||data.optBoolean("drm")) return null;
        VideoInfo info=new VideoInfo(); info.id=id; info.sourceUrl=info.pageUrl=source; info.platform="视频号"; info.userAgent=VideoResolver.DESKTOP_UA;
        info.description=data.optString("description"); info.title=info.description.isEmpty()?"视频号视频 "+id:info.description.split("\\n",2)[0];
        info.author=data.optString("author"); info.thumbnail=Platforms.media(data.optString("cover_url"),"视频号"); info.duration=data.optDouble("duration",0);
        for (String key:new String[]{"h264_url","h265_url"}) {
            String url=data.optString(key); if (url.isEmpty()||url.equals(data.optString("cover_url"))) continue;
            try {
                URI uri=new URI(url); if (!"https".equalsIgnoreCase(uri.getScheme())||uri.getUserInfo()!=null) continue;
                if (!Platforms.host(url,"finder.video.qq.com")&&!Platforms.host(url,"video.weixin.qq.com")&&!Platforms.host(url,"wxapp.tc.qq.com")) continue;
                if (url.toLowerCase(java.util.Locale.ROOT).contains(".m3u8")) continue;
            } catch (Exception e) { continue; }
            boolean duplicate=false; for (VideoInfo.Format format:info.formats) if (format.url.equals(url)) duplicate=true;
            if (!duplicate) info.formats.add(new VideoInfo.Format(url,key.equals("h264_url")?"兼容版本 · H.264":"省空间版本 · H.265",0,0,0));
        }
        return info.formats.isEmpty()?null:info;
    }
}
