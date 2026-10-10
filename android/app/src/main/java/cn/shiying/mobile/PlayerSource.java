package cn.shiying.mobile;

import android.content.Context;
import android.net.Uri;
import android.webkit.CookieManager;
import cn.shiying.mobile.core.ChannelsCodec;
import cn.shiying.mobile.core.MediaHeaders;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Playback preparation uses private cache only, never download or gallery records. */
final class PlayerSource {
    static final class Ready {
        final Uri uri; final Map<String,String> headers;
        Ready(Uri uri,Map<String,String> headers) { this.uri=uri; this.headers=headers; }
    }
    private final Context context;
    private final VideoResolver.Status status;
    private final File directory;
    private volatile boolean cancelled;
    private volatile HttpURLConnection connection;
    private static final long LIMIT=1024L*1024*1024;
    PlayerSource(Context context,VideoResolver.Status status) {
        this.context=context.getApplicationContext(); this.status=status;
        directory=new File(context.getCacheDir(),"player_"+UUID.randomUUID());
    }
    private void check() throws InterruptedException {
        if (cancelled||Thread.currentThread().isInterrupted()) throw new InterruptedException();
    }
    static Map<String,String> headers(VideoInfo info,String url) {
        Map<String,String> result=new HashMap<>(); result.put("User-Agent",info.userAgent);
        result.put("Referer",VideoResolver.referer(info)); result.put("Accept-Encoding","identity");
        String cookies=CookieManager.getInstance().getCookie(url);
        if (cookies!=null&&!cookies.isEmpty()) result.put("Cookie",cookies);
        result.put("android-allow-cross-domain-redirect","0"); return result;
    }
    Ready prepare(VideoInfo info,int index,boolean cacheDirect) throws Exception {
        boolean success=false;
        try {
            check(); prune(); if (info.isImages()||index<0||index>=info.formats.size()) throw new Exception("请选择视频格式后播放。");
            VideoInfo.Format format=info.formats.get(index);
            VideoResolver resolver=new VideoResolver(new VideoResolver.Cookies() {
                public String get(String url) { return CookieManager.getInstance().getCookie(url); }
                public void save(String url,String value) { CookieManager.getInstance().setCookie(url,value); }
            },status);
            List<VideoInfo.Asset> assets=info.selectedAssets(format);
            if (assets.isEmpty()) throw new Exception("没有可播放的视频。");
            if ("direct".equals(format.mode)&&assets.size()==1&&!cacheDirect&&assets.get(0).decodeKey.isEmpty()) {
                VideoResolver.Page page=resolver.probe(info,assets.get(0)); check(); success=true;
                return new Ready(Uri.parse(page.url),headers(info,page.url));
            }
            if (!directory.mkdirs()) throw new Exception("无法创建播放缓存。");
            List<Uri> files=new ArrayList<>(); List<String> kinds=new ArrayList<>(); long total=0;
            for (int i=0;i<assets.size();i++) {
                check(); VideoInfo.Asset asset=assets.get(i); VideoResolver.Page page=resolver.probe(info,asset);
                if (page.size>LIMIT||total+page.size>LIMIT) throw new Exception("视频较大，请先保存到手机，再从我的片段播放。");
                if (page.size>0&&directory.getUsableSpace()<2*page.size+64*1024*1024L) throw new Exception("播放缓存空间不足，请释放手机空间。");
                status.show("dash".equals(format.mode)?"正在准备画面和声音…":"正在准备播放缓存…");
                File part=new File(directory,"part_"+i+".mp4"); total+=copy(info,page,asset,part,total);
                files.add(Uri.fromFile(part)); kinds.add(asset.kind);
            }
            check(); File ready;
            if (("direct".equals(format.mode)||"channels".equals(format.mode))&&files.size()==1) ready=new File(files.get(0).getPath());
            else {
                status.show("正在合并画面和声音…"); ready=new File(directory,"play.mp4");
                MediaAssembler.mux(context,-System.nanoTime(),files,kinds,format.mode,ready);
                for (Uri part:files) new File(part.getPath()).delete();
            }
            check(); success=true; return new Ready(Uri.fromFile(ready),new HashMap<>());
        } finally { connection=null; if (!success||cancelled) remove(directory); }
    }
    private long copy(VideoInfo info,VideoResolver.Page page,VideoInfo.Asset asset,File file,long previous) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL(page.url).openConnection(); connection=c;
        c.setInstanceFollowRedirects(false); c.setConnectTimeout(12000); c.setReadTimeout(15000);
        for (Map.Entry<String,String> header:headers(info,page.url).entrySet()) if (!header.getKey().startsWith("android-")) c.setRequestProperty(header.getKey(),header.getValue());
        ChannelsCodec codec=asset.decodeKey.isEmpty()?null:new ChannelsCodec(asset.decodeKey); long bytes=0,last=0;
        try {
            check(); if (c.getResponseCode()!=200) throw new Exception("视频地址暂不可用，请返回重新解析。");
            try (InputStream input=c.getInputStream();FileOutputStream output=new FileOutputStream(file)) {
                byte[] buffer=new byte[65536]; byte[] head=new byte[64]; int headSize=0,n;
                while ((n=input.read(buffer))!=-1) {
                    check(); bytes+=n;
                    if (previous+bytes>LIMIT||directory.getUsableSpace()<64*1024*1024L) throw new Exception("播放缓存空间不足或视频过大，请先保存再播放。");
                    if (codec!=null) codec.apply(buffer,0,n);
                    int take=Math.min(n,head.length-headSize); if (take>0) { System.arraycopy(buffer,0,head,headSize,take); headSize+=take; }
                    output.write(buffer,0,n);
                    long now=System.currentTimeMillis(); if (now-last>500) { last=now; status.show(String.format(java.util.Locale.ROOT,"正在准备播放 · %.1f MB",(previous+bytes)/(1024.0*1024))); }
                }
                if (MediaHeaders.detect(head,headSize,"video")==null) throw new Exception("地址返回的不是有效媒体，请返回重新解析。");
            }
            if (page.size>0&&bytes<page.size) throw new Exception("视频未传输完整，请重试。"); return bytes;
        } finally { c.disconnect(); connection=null; }
    }
    void close() { cancelled=true; HttpURLConnection c=connection; if (c!=null) c.disconnect(); remove(directory); }
    private void prune() {
        File[] folders=context.getCacheDir().listFiles(); if (folders==null) return;
        long deadline=System.currentTimeMillis()-24*60*60*1000L;
        for (File folder:folders) if (folder.isDirectory()&&folder.getName().matches("player_[0-9a-f-]{36}")&&folder.lastModified()<deadline) remove(folder);
    }
    private static void remove(File file) { File[] children=file.listFiles(); if (children!=null) for (File child:children) remove(child); file.delete(); }
}
