package cn.shiying.mobile.core;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

public final class VideoInfo {
    public String id = "", title = "", author = "", pageUrl = "", sourceUrl = "", thumbnail = "", userAgent = VideoResolver.DESKTOP_UA;
    public double duration;
    public String description="", platform="", kind="video";
    public final List<Format> formats = new ArrayList<>();

    public static final class Format {
        public String url, label, mode="direct";
        public int width, height;
        public long size;
        public final List<Asset> assets=new ArrayList<>();
        public final List<String> alternatives=new ArrayList<>();
        public Format(String url, String label, int width, int height, long size) {
            this.url = url; this.label = label; this.width = width; this.height = height; this.size = size;
        }
    }

    public static final class Asset {
        public String url, kind;
        public String decodeKey="";
        public int index;
        public final List<String> alternatives=new ArrayList<>();
        public Asset(String url,String kind,int index) { this.url=url; this.kind=kind; this.index=index; }
    }
    public boolean isImages() { return "images".equals(kind); }
    public List<Asset> selectedAssets(Format f) {
        if (!f.assets.isEmpty()) return new ArrayList<>(f.assets);
        List<Asset> result=new ArrayList<>(); Asset asset=new Asset(f.url,isImages()?"image":"video",1);
        asset.alternatives.addAll(f.alternatives); result.add(asset); return result;
    }
    public int imageCount() { return isImages()&&!formats.isEmpty()?formats.get(0).assets.size():0; }

    public JSONObject toJson() throws Exception {
        JSONObject o = new JSONObject();
        o.put("id", id).put("title", title).put("author", author).put("pageUrl", pageUrl).put("sourceUrl", sourceUrl)
            .put("thumbnail", thumbnail).put("userAgent", userAgent).put("duration",Double.isNaN(duration)||Double.isInfinite(duration)?0:duration)
            .put("description",description).put("platform",platform).put("kind",kind);
        JSONArray list = new JSONArray();
        for (Format f : formats) {
            JSONArray assets=new JSONArray();
            for (Asset a:f.assets) assets.put(new JSONObject().put("url",a.url).put("kind",a.kind).put("index",a.index).put("alternatives",new JSONArray(a.alternatives)).put("decodeKey",a.decodeKey));
            list.put(new JSONObject().put("url", f.url).put("label", f.label)
                .put("width", f.width).put("height", f.height).put("size", f.size).put("assets",assets).put("alternatives",new JSONArray(f.alternatives)).put("mode",f.mode));
        }
        return o.put("formats", list);
    }

    public static VideoInfo fromJson(JSONObject o) {
        VideoInfo v = new VideoInfo();
        v.id = o.optString("id"); v.title = o.optString("title"); v.author = o.optString("author");
        v.pageUrl = o.optString("pageUrl"); v.sourceUrl = o.optString("sourceUrl"); v.thumbnail = o.optString("thumbnail");
        v.userAgent = o.optString("userAgent", VideoResolver.DESKTOP_UA); v.duration = o.optDouble("duration", 0);
        v.description=o.optString("description"); v.platform=o.optString("platform"); v.kind=o.optString("kind","video");
        JSONArray list = o.optJSONArray("formats");
        if (list != null) for (int i = 0; i < list.length(); i++) {
            JSONObject f = list.optJSONObject(i);
            if (f != null) {
                Format format=new Format(f.optString("url"), f.optString("label"), f.optInt("width"), f.optInt("height"), f.optLong("size"));
                format.mode=f.optString("mode","direct");
                JSONArray alternatives=f.optJSONArray("alternatives");
                if (alternatives!=null) for (int j=0;j<alternatives.length();j++) format.alternatives.add(alternatives.optString(j));
                JSONArray assets=f.optJSONArray("assets");
                if (assets!=null) for (int j=0;j<assets.length();j++) { JSONObject a=assets.optJSONObject(j); if (a!=null) {
                    Asset asset=new Asset(a.optString("url"),a.optString("kind","video"),a.optInt("index",j+1)); JSONArray backup=a.optJSONArray("alternatives");
                    asset.decodeKey=a.optString("decodeKey");
                    if (backup!=null) for (int k=0;k<backup.length();k++) asset.alternatives.add(backup.optString(k)); format.assets.add(asset);
                } }
                v.formats.add(format);
            }
        }
        return v;
    }
}
