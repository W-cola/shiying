package cn.shiying.mobile.core;

import java.net.URI;
import java.net.URLDecoder;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

/** Exact platform hosts and identifiers; never infer targets from recommendation data. */
public final class Platforms {
    public static boolean host(String url,String domain) {
        try { String h=new URI(url).getHost(); return h!=null&&(h.equalsIgnoreCase(domain)||h.toLowerCase(Locale.ROOT).endsWith("."+domain)); }
        catch (Exception e) { return false; }
    }
    public static String name(String url) {
        if (VideoResolver.isDouyin(url)) return "抖音";
        if (Xiaohongshu.supports(url)) return "小红书";
        if (host(url,"bilibili.com")||host(url,"b23.tv")) return "B站";
        if (host(url,"kuaishou.com")||host(url,"gifshow.com")||host(url,"kwai.com")||host(url,"chenzhongtech.com")) return "快手";
        if (host(url,"channels.weixin.qq.com")||host(url,"finder.video.qq.com")||(host(url,"weixin.qq.com")&&sphPath(url))) return "视频号";
        return "";
    }
    public static boolean known(String url) { return !name(url).isEmpty(); }
    private static boolean sphPath(String url) { try { return new URI(url).getPath().startsWith("/sph/"); } catch (Exception e) { return false; } }
    public static String query(String url,String... keys) {
        try { String q=new URI(url).getRawQuery(); if (q==null) return "";
            for (String pair:q.split("&")) { String[] p=pair.split("=",2); if (p.length<2) continue;
                for (String key:keys) if (key.equals(p[0])) return URLDecoder.decode(p[1],"UTF-8");
            }
        } catch (Exception ignored) { } return "";
    }
    public static String id(String url) {
        String platform=name(url),path;
        try { path=new URI(url).getPath(); } catch (Exception e) { return ""; }
        if ("B站".equals(platform)) {
            Matcher m=Pattern.compile("/(?:video/)?(BV[0-9A-Za-z]{10}|av[0-9]+)(?:/|$)",Pattern.CASE_INSENSITIVE).matcher(path);
            if (m.find()) { String value=m.group(1); return value.regionMatches(true,0,"BV",0,2)?"BV"+value.substring(2):value.toLowerCase(Locale.ROOT); }
            m=Pattern.compile("/(?:opus/|read/cv)([0-9]+)(?:/|$)").matcher(path); if (m.find()) return path.contains("/read/cv")?"cv"+m.group(1):"opus"+m.group(1);
            if (host(url,"t.bilibili.com")&&path.matches("/[0-9]+/?")) return "opus"+path.replace("/","");
            String bv=query(url,"bvid"); if (bv.matches("BV[0-9A-Za-z]{10}")) return bv;
        } else if ("快手".equals(platform)) {
            Matcher m=Pattern.compile("/(?:short-video|fw/photo|photo)/([A-Za-z0-9_-]+)").matcher(path); if (m.find()) return m.group(1);
            String photo=query(url,"photoId","photo_id"); if (photo.matches("[A-Za-z0-9_-]+")) return photo;
        } else if ("视频号".equals(platform)) {
            String share=ChannelsService.shareId(url); if (!share.isEmpty()) return share;
            if (path.equals("/finder-preview/pages/sph")) return query(url,"id");
            String feed=query(url,"objectId","object_id","feedId","finderFeedId","eid"); if (!feed.isEmpty()) return feed;
            Matcher m=Pattern.compile("/(?:feed|video)/([A-Za-z0-9_-]+)").matcher(path); if (m.find()) return m.group(1);
        }
        return "";
    }
    public static boolean samePlatform(String source,String page) { String p=name(source); return !p.isEmpty()&&p.equals(name(page)); }
    public static String media(String raw,String platform) {
        if (raw==null||raw.isEmpty()) return ""; String url=raw.startsWith("//")?"https:"+raw:raw;
        if (url.startsWith("http://")) {
            boolean official=false;
            String[] domains="B站".equals(platform)?new String[]{"bilivideo.com","bilivideo.cn","hdslb.com","bilibili.com"}:
                "快手".equals(platform)?new String[]{"kwimgs.com","yximgs.com","kwaicdn.com","kuaishoucdn.com","kuaishou.com"}:
                new String[]{"video.qq.com","qpic.cn","wxapp.tc.qq.com","finder.video.qq.com"};
            for (String domain:domains) if (host(url,domain)) official=true;
            if (!official) return ""; url="https:"+url.substring(5);
        }
        try { URI u=new URI(url); return "https".equalsIgnoreCase(u.getScheme())&&u.getHost()!=null&&u.getUserInfo()==null?url:""; }
        catch (Exception e) { return ""; }
    }
}
