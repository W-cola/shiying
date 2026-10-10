package cn.shiying.mobile.core;

import org.json.JSONArray;
import org.json.JSONObject;

/** Shared ordered picture formats and platform-neutral caption export. */
public final class Albums {
    public static boolean add(VideoInfo info,JSONArray pictures,String platform) {
        if (pictures==null||pictures.length()==0) return false;
        VideoInfo.Format all=new VideoInfo.Format("","全部图片",0,0,0);
        for (int i=0;i<pictures.length();i++) {
            Object raw=pictures.opt(i); JSONObject image=raw instanceof JSONObject?(JSONObject)raw:null;
            String url=raw instanceof String?(String)raw:image==null?"":image.optString("url",image.optString("src",image.optString("urlDefault")));
            url=Platforms.media(url,platform); if (url.isEmpty()) return false;
            int w=image==null?0:image.optInt("width"),h=image==null?0:image.optInt("height");
            VideoInfo.Asset asset=new VideoInfo.Asset(url,"image",i+1); all.assets.add(asset);
            JSONArray backups=image==null?null:image.optJSONArray("alternatives"); if (backups!=null) for (int b=0;b<backups.length();b++) { String backup=Platforms.media(backups.optString(b),platform); if (!backup.isEmpty()&&!backup.equals(url)&&!asset.alternatives.contains(backup)) asset.alternatives.add(backup); }
            VideoInfo.Format one=new VideoInfo.Format(url,"第 "+(i+1)+" 张"+(w>0&&h>0?" · "+w+" × "+h:""),w,h,0); one.assets.add(asset); info.formats.add(one);
        }
        info.kind="images"; all.url=all.assets.get(0).url; all.label="全部图片 · "+all.assets.size()+" 张"; info.formats.add(0,all); info.thumbnail=all.url; return true;
    }
    public static String text(VideoInfo info) {
        String source=info.pageUrl;
        try { java.net.URI u=new java.net.URI(source); source=new java.net.URI(u.getScheme(),u.getAuthority(),u.getPath(),null,null).toString(); } catch (Exception ignored) { }
        return info.title+"\n\n作者："+info.author+"\n平台："+info.platform+"\n内容编号："+info.id+"\n来源："+source+"\n\n"+info.description+"\n";
    }
}
