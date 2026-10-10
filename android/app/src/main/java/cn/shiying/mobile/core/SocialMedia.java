package cn.shiying.mobile.core;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.HashSet;
import java.util.Set;

/** Target-bound normal page data for Kuaishou and WeChat Channels. */
public final class SocialMedia {
    public static VideoInfo fromPayload(Object payload,String target,String source,String page) {
        String platform=Platforms.name(source); if (!"快手".equals(platform)&&!"视频号".equals(platform)) platform=Platforms.name(page);
        if (target.isEmpty()) return null;
        ArrayDeque<Object> queue=new ArrayDeque<>(); if (payload instanceof JSONObject||payload instanceof JSONArray) queue.add(payload); int visited=0;
        while (!queue.isEmpty()&&visited++<60000) {
            Object value=queue.removeFirst();
            if (value instanceof JSONObject) {
                JSONObject object=(JSONObject)value;
                if ("视频号".equals(platform)) { VideoInfo preview=preview(object,target,source,page); if (preview!=null) return preview; }
                if ("快手".equals(platform)) {
                    JSONObject cache=object.optJSONObject("defaultClient");
                    JSONObject cached=cache==null?null:cache.optJSONObject("VisionVideoDetailPhoto:"+target);
                    if (cached!=null&&(cached.optString("photoId").isEmpty()||target.equals(cached.optString("photoId")))) try {
                        JSONObject photo=(JSONObject)unpack(cached,cache,new HashSet<>(),0,new int[]{10000}); photo.put("photoId",target);
                        VideoInfo info=kuaishou(photo,target,source,page); if (info!=null) return info;
                    } catch (Exception ignored) { }
                }
                boolean matches=false; for (String key:new String[]{"photoId","photo_id","objectId","object_id","feedId","id","encryptedObjectId","encrypted_objectid"}) if (target.equals(object.optString(key))) matches=true;
                if ("快手".equals(platform)) { matches|=kuaishouTarget(object,target,page); JSONObject photo=object.optJSONObject("photo"); if (photo!=null) matches|=kuaishouTarget(photo,target,page); }
                if (matches) {
                    VideoInfo info="快手".equals(platform)?kuaishou(object,target,source,page):channels(object,target,source,page);
                    if (info!=null) return info;
                }
                Iterator<String> keys=object.keys(); while (keys.hasNext()) { Object child=object.opt(keys.next()); if (child instanceof JSONObject||child instanceof JSONArray) queue.add(child); }
            } else { JSONArray array=(JSONArray)value; for (int i=0;i<array.length();i++) { Object child=array.opt(i); if (child instanceof JSONObject||child instanceof JSONArray) queue.add(child); } }
        }
        return null;
    }
    private static VideoInfo base(JSONObject object,String id,String source,String page,String platform) {
        VideoInfo info=new VideoInfo(); info.id=id; info.sourceUrl=source; info.pageUrl=page; info.platform=platform;
        info.description=first(object,"caption","description","desc","title"); info.title=info.description.isEmpty()?platform+"内容 "+id:info.description.split("\\n",2)[0];
        JSONObject author=object.optJSONObject("author"); if (author==null) author=object.optJSONObject("user");
        if (author!=null) info.author=first(author,"name","nickname","userName","nickName");
        if (info.author.isEmpty()) info.author=first(object,"userName","nickName");
        info.duration=object.optDouble("duration",0)/1000.0; info.thumbnail=Platforms.media(first(object,"coverUrl","cover","poster"),platform); return info;
    }
    private static VideoInfo kuaishou(JSONObject photo,String target,String source,String page) {
        JSONObject nested=photo.optJSONObject("photo");
        if (nested!=null) try {
            String childId=first(nested,"photoId","photo_id","id"); if (!childId.isEmpty()&&!kuaishouTarget(nested,target,page)) return null;
            JSONObject merged=new JSONObject(photo.toString()); Iterator<String> keys=nested.keys(); while (keys.hasNext()) { String key=keys.next(); merged.put(key,nested.opt(key)); } photo=merged;
        } catch (Exception e) { return null; }
        VideoInfo info=base(photo,target,source,page,"快手");
        JSONObject atlas=photo.optJSONObject("atlas"); if (atlas==null) atlas=photo.optJSONObject("imageAtlas");
        JSONObject extra=photo.optJSONObject("ext_params");
        if (extra==null) try { extra=new JSONObject(photo.optString("ext_params")); } catch (Exception ignored) { }
        if (atlas==null&&extra!=null) atlas=extra.optJSONObject("atlas");
        JSONArray images=photo.optJSONArray("images"); if (images==null) images=photo.optJSONArray("imgUrls");
        Object rawAtlas=extra==null?null:extra.opt("atlas");
        if (rawAtlas instanceof String) try { rawAtlas=new org.json.JSONTokener((String)rawAtlas).nextValue(); } catch (Exception ignored) { }
        if (rawAtlas instanceof JSONArray) {
            JSONArray list=(JSONArray)rawAtlas; images=new JSONArray();
            for (int i=0;i<list.length();i++) {
                Object entry=list.opt(i); JSONObject image=entry instanceof JSONObject?(JSONObject)entry:null;
                JSONArray cdns=image==null?null:image.optJSONArray("cdnUrls");
                images.put(cdns!=null&&cdns.length()>0?cdns.opt(0):entry);
            }
        }
        if (atlas!=null) {
            JSONArray list=atlas.optJSONArray("list"); if (list==null) list=atlas.optJSONArray("images");
            if (list!=null) {
                images=new JSONArray(); java.util.List<String> cdns=atlasCdns(atlas); JSONArray sizes=atlas.optJSONArray("size");
                for (int i=0;i<list.length();i++) {
                    Object raw=list.opt(i); if (raw instanceof String) {
                        String url=(String)raw; JSONArray alternatives=new JSONArray();
                        if (!url.startsWith("http")&&!url.startsWith("//")) {
                            if (cdns.isEmpty()) return null; String path=url.replaceFirst("^/",""); url=cdns.get(0)+path;
                            for (int c=1;c<cdns.size();c++) alternatives.put(cdns.get(c)+path);
                        }
                        try { JSONObject size=sizes==null?null:sizes.optJSONObject(i); images.put(new JSONObject().put("url",url).put("alternatives",alternatives).put("width",size==null?0:size.optInt("w",size.optInt("width"))).put("height",size==null?0:size.optInt("h",size.optInt("height")))); } catch (Exception e) { return null; }
                    } else images.put(raw);
                }
            }
        }
        String photoType=photo.optString("photoType").toUpperCase(java.util.Locale.ROOT);
        boolean imagePost=atlas!=null||rawAtlas instanceof JSONArray||"image".equalsIgnoreCase(photo.optString("type"))||"atlas".equalsIgnoreCase(photo.optString("type"))||photoType.contains("ATLAS")||photoType.equals("IMAGE")||photo.optInt("photoType")==2;
        if (imagePost) return Albums.add(info,images,"快手")?info:null;
        Set<String> seen=new HashSet<>();
        for (String key:new String[]{"playUrl","videoUrl","downloadUrl","url","photoUrl","photoH265Url"}) add(info,photo.optString(key),photo.optInt("width"),photo.optInt("height"),seen);
        JSONArray mobile=photo.optJSONArray("mainMvUrls"); if (mobile!=null) for (int i=0;i<mobile.length();i++) { JSONObject item=mobile.optJSONObject(i); if (item!=null) add(info,item.optString("url"),photo.optInt("width"),photo.optInt("height"),seen); }
        JSONObject video=photo.optJSONObject("video"); if (video!=null) for (String key:new String[]{"playUrl","videoUrl","url"}) add(info,video.optString(key),video.optInt("width"),video.optInt("height"),seen);
        JSONObject resource=photo.optJSONObject("videoResource"); if (resource!=null) representations(info,resource,seen);
        for (String key:new String[]{"manifest","manifestH265"}) { JSONObject manifest=photo.optJSONObject(key); if (manifest!=null) representations(info,manifest,seen); }
        info.formats.sort((a,b)->Integer.compare(b.height,a.height)); return info.formats.isEmpty()?null:info;
    }
    private static boolean kuaishouTarget(JSONObject photo,String target,String page) {
        String actual=first(photo,"photoId","photo_id","id"); if (actual.equals(target)) return true;
        if (actual.isEmpty()) return false;
        String alias=Platforms.query("https://www.kuaishou.com/?"+photo.optString("share_info"),"photoId");
        if (!target.equals(alias)||!target.equals(Platforms.id(page))) return false;
        String numeric=Platforms.query(page,"shareObjectId"); return numeric.isEmpty()||actual.equals(numeric);
    }
    private static java.util.List<String> atlasCdns(JSONObject atlas) {
        java.util.List<String> result=new java.util.ArrayList<>();
        for (String key:new String[]{"cdn","cdnUrl","cdnList"}) {
            Object raw=atlas.opt(key); JSONArray values=raw instanceof JSONArray?(JSONArray)raw:new JSONArray().put(raw==null?JSONObject.NULL:raw);
            for (int i=0;i<values.length();i++) {
                Object item=values.opt(i); String value=item instanceof JSONObject?((JSONObject)item).optString("cdn"):item instanceof String?(String)item:"";
                if (value.isEmpty()) continue;
                if (!value.startsWith("https://")&&!value.startsWith("http://")&&!value.startsWith("//")) value="https://"+value;
                String url=Platforms.media(value,"快手"); if (url.isEmpty()) continue; if (!url.endsWith("/")) url+="/"; if (!result.contains(url)) result.add(url);
            }
        } return result;
    }
    private static void representations(VideoInfo info,Object value,Set<String> seen) {
        if (value instanceof JSONObject) {
            JSONObject o=(JSONObject)value; if (o.optBoolean("drm")||o.optBoolean("hasDrm")) return;
            if (o.has("url")&&(o.has("width")||o.has("height")||o.has("qualityType"))) {
                for (String key:new String[]{"url","backupUrl"}) {
                    Object raw=o.opt(key); if (raw instanceof JSONObject) raw=((JSONObject)raw).opt("json");
                    if (raw instanceof String) add(info,(String)raw,o.optInt("width"),o.optInt("height"),seen);
                    else if (raw instanceof JSONArray) for (int i=0;i<((JSONArray)raw).length();i++) add(info,((JSONArray)raw).optString(i),o.optInt("width"),o.optInt("height"),seen);
                }
            }
            Iterator<String> keys=o.keys(); while (keys.hasNext()) { Object child=o.opt(keys.next()); if (child instanceof JSONObject||child instanceof JSONArray) representations(info,child,seen); }
        } else if (value instanceof JSONArray) for (int i=0;i<((JSONArray)value).length();i++) representations(info,((JSONArray)value).opt(i),seen);
    }
    /** Expand only references in this page's published Apollo cache, with bounded cycles. */
    private static Object unpack(Object value,JSONObject cache,Set<String> active,int depth,int[] budget) throws Exception {
        if (depth>20||--budget[0]<0) throw new Exception("网页数据层级过深。");
        if (value instanceof JSONObject) {
            JSONObject object=(JSONObject)value; String ref=object.optString("__ref"); if (ref.isEmpty()&&"id".equals(object.optString("type"))) ref=object.optString("id");
            if (!ref.isEmpty()&&cache.has(ref)) {
                if (!active.add(ref)) return JSONObject.NULL;
                Object result=unpack(cache.opt(ref),cache,active,depth+1,budget); active.remove(ref); return result;
            }
            JSONObject result=new JSONObject(); Iterator<String> keys=object.keys(); while (keys.hasNext()) { String key=keys.next(); result.put(key,unpack(object.opt(key),cache,active,depth+1,budget)); } return result;
        }
        if (value instanceof JSONArray) { JSONArray result=new JSONArray(); for (int i=0;i<((JSONArray)value).length();i++) result.put(unpack(((JSONArray)value).opt(i),cache,active,depth+1,budget)); return result; }
        return value;
    }
    private static VideoInfo channels(JSONObject feed,String target,String source,String page) {
        JSONObject desc=feed.optJSONObject("objectDesc"); if (desc==null) desc=feed.optJSONObject("object_desc"); if (desc==null) desc=feed;
        JSONArray media=desc.optJSONArray("media"); if (media==null) media=desc.optJSONArray("mediaList"); if (media==null||media.length()==0) return null;
        VideoInfo info=base(feed,target,source,page,"视频号"); info.description=first(desc,"description","desc"); if (!info.description.isEmpty()) info.title=info.description.split("\\n",2)[0];
        JSONObject contact=feed.optJSONObject("contact"); if (contact!=null) info.author=first(contact,"nickname","nickName");
        JSONArray pictures=new JSONArray(); Set<String> seen=new HashSet<>(); boolean allImages=true;
        for (int i=0;i<media.length();i++) {
            JSONObject item=media.optJSONObject(i); if (item==null||item.optBoolean("drm")) return null;
            String decode=first(item,"decodeKey","decode_key");
            if (!decode.isEmpty()&&!decode.equals("0")) try { new ChannelsCodec(decode); } catch (Exception e) { return null; }
            String url=first(item,"url","videoUrl","imageUrl"); String token=item.optString("urlToken");
            if (!token.isEmpty()&&(token.startsWith("?")||token.startsWith("&"))) url+=token;
            int type=item.optInt("mediaType",item.optInt("type",desc.optInt("mediaType",0))); if (type==9) return null;
            if (type==2||"image".equals(item.optString("type"))) {
                try { pictures.put(new JSONObject().put("url",url).put("width",item.optInt("width")).put("height",item.optInt("height"))); } catch (Exception e) { return null; }
            } else {
                allImages=false; int before=info.formats.size(); add(info,url,item.optInt("width"),item.optInt("height"),seen);
                if (!decode.isEmpty()&&!decode.equals("0")&&info.formats.size()>before) {
                    VideoInfo.Format format=info.formats.get(info.formats.size()-1); format.mode="channels"; VideoInfo.Asset asset=new VideoInfo.Asset(format.url,"video",1); asset.decodeKey=decode; format.assets.add(asset);
                }
                info.duration=Math.max(info.duration,item.optDouble("videoPlayLen",item.optDouble("duration",0)));
                if (info.thumbnail.isEmpty()) info.thumbnail=Platforms.media(first(item,"thumbUrl","coverUrl"),"视频号");
            }
        }
        if (allImages) return Albums.add(info,pictures,"视频号")?info:null;
        return info.formats.isEmpty()?null:info;
    }
    private static VideoInfo preview(JSONObject root,String target,String source,String page) {
        String context=root.optString("previewPage"); JSONObject feed=root.optJSONObject("feedInfo"),author=root.optJSONObject("authorInfo");
        if (context.isEmpty()) {
            String request=root.optString("requestUrl");
            try { if (!Platforms.host(request,"channels.weixin.qq.com")||!new java.net.URI(request).getPath().equals("/finder-preview/api/feed/get_feed_info")) return null; } catch (Exception e) { return null; }
            context=Platforms.query(request,"_pageUrl"); JSONObject response=root.optJSONObject("response"),data=response==null?null:response.optJSONObject("data");
            if (response==null||response.optInt("errCode",-1)!=0||data==null) return null; feed=data.optJSONObject("feedInfo"); author=data.optJSONObject("authorInfo");
        }
        if (!Platforms.samePlatform(page,context)||!target.equals(Platforms.id(context))||feed==null||feed.optBoolean("drm")) return null;
        try { if (!new java.net.URI(context).getPath().equals("/finder-preview/pages/sph")) return null; } catch (Exception e) { return null; }
        VideoInfo info=base(feed,target,source,page,"视频号"); if (author!=null) info.author=author.optString("nickname"); info.thumbnail=Platforms.media(feed.optString("coverUrl"),"视频号");
        JSONArray pictures=feed.optJSONArray("picInfo");
        if (pictures!=null&&pictures.length()>0) {
            JSONArray images=new JSONArray(); for (int i=0;i<pictures.length();i++) { JSONObject picture=pictures.optJSONObject(i); if (picture==null) return null; try { images.put(new JSONObject().put("url",first(picture,"url","picUrl","imageUrl")).put("width",picture.optInt("width")).put("height",picture.optInt("height"))); } catch (Exception e) { return null; } }
            return Albums.add(info,images,"视频号")?info:null;
        }
        Set<String> seen=new HashSet<>(); for (String key:new String[]{"h264VideoInfo","h265VideoInfo"}) { JSONObject video=feed.optJSONObject(key); if (video!=null&&!video.optBoolean("drm")) add(info,video.optString("videoUrl"),video.optInt("width"),video.optInt("height"),seen); }
        add(info,feed.optString("videoUrl"),feed.optInt("width"),feed.optInt("height"),seen);
        return info.formats.isEmpty()?null:info;
    }
    private static void add(VideoInfo info,String raw,int width,int height,Set<String> seen) {
        String url=Platforms.media(raw,info.platform); if (url.isEmpty()||url.toLowerCase(java.util.Locale.ROOT).contains(".m3u8")||!seen.add(url)) return;
        info.formats.add(new VideoInfo.Format(url,width>0&&height>0?width+" × "+height:"公开播放画质",width,height,0));
    }
    private static String first(JSONObject object,String... keys) { for (String key:keys) { String value=object.optString(key); if (!value.isEmpty()&&!value.equals("null")) return value; } return ""; }
}
