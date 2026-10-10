package cn.shiying.mobile;

import android.app.DownloadManager;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.CookieManager;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import cn.shiying.mobile.core.Xiaohongshu;
import cn.shiying.mobile.core.Albums;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Media scheduling and local note-text export; no UI controls are defined here. */
final class DownloadCoordinator {
    static final class Prepared {
        final VideoInfo.Asset asset;
        final VideoResolver.Page media;
        final String mode;
        Prepared(VideoInfo.Asset asset,VideoResolver.Page media) { this(asset,media,"direct"); }
        Prepared(VideoInfo.Asset asset,VideoResolver.Page media,String mode) { this.asset=asset; this.media=media; this.mode=mode; }
    }
    static List<Prepared> prepare(VideoResolver resolver,VideoInfo info,VideoInfo.Format selection) throws Exception {
        List<Prepared> list=new ArrayList<>();
        for (VideoInfo.Asset asset:info.selectedAssets(selection)) {
            if (Thread.currentThread().isInterrupted()) throw new Exception("任务已取消。");
            try { list.add(new Prepared(asset,resolver.probe(info,asset),selection.mode)); }
            catch (Exception e) { throw new Exception((info.isImages()?"第 "+asset.index+" 张图片：":"")+e.getMessage(),e); }
        }
        return list;
    }
    static JSONArray enqueue(Context context,DownloadManager downloads,VideoInfo info,List<Prepared> media) throws Exception {
        if (!info.isImages()&&!media.isEmpty()&&!"direct".equals(media.get(0).mode)) return CompoundDownloads.enqueue(context,downloads,info,media);
        String stamp=new SimpleDateFormat("yyyyMMdd_HHmmss_SSS",Locale.ROOT).format(new Date());
        String stem=VideoResolver.filename(info.title,info.id)+" "+stamp;
        String albumBatch=info.isImages()?java.util.UUID.randomUUID().toString():"";
        JSONArray records=new JSONArray(); List<Long> jobs=new ArrayList<>(); Uri textUri=null; File legacyText=null;
        try {
            for (Prepared item:media) {
                String suffix=info.isImages()?String.format(Locale.ROOT,"_%03d",item.asset.index):"";
                String name=stem+suffix+"."+item.media.ext;
                String title=info.title+(info.isImages()?" · 图片 "+item.asset.index+"/"+info.imageCount():"");
                DownloadManager.Request request=new DownloadManager.Request(Uri.parse(item.media.url));
                request.setTitle(title); request.setDescription("拾影 · 保存你的灵感"); request.setMimeType(item.media.mime);
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setAllowedOverMetered(true); request.setAllowedOverRoaming(false);
                request.addRequestHeader("User-Agent",info.userAgent); request.addRequestHeader("Referer",VideoResolver.referer(info)); request.addRequestHeader("Accept-Encoding","identity");
                String cookie=CookieManager.getInstance().getCookie(item.media.url); if (cookie!=null&&!cookie.isEmpty()) request.addRequestHeader("Cookie",cookie);
                String directory="video".equals(item.asset.kind)?Environment.DIRECTORY_MOVIES:Environment.DIRECTORY_PICTURES;
                // DownloadManager appends this as an encoded URI path; a caption's # or % must remain part of the filename.
                request.setDestinationInExternalPublicDir(directory,Uri.encode("拾影/"+name,"/"));
                request.allowScanningByMediaScanner();
                long id=downloads.enqueue(request); jobs.add(id);
                JSONObject row=record(info,id,title,name,item.media.mime).put("kind",item.asset.kind).put("directory",directory);
                if (info.isImages()) row.put("albumBatch",albumBatch).put("albumTitle",info.title).put("description",info.description).put("imageIndex",item.asset.index);
                records.put(row);
            }
            if (info.isImages()) {
                byte[] body=Albums.text(info).getBytes(StandardCharsets.UTF_8);
                String name=stem+"_正文.txt";
                if (Build.VERSION.SDK_INT>=29) {
                    ContentValues values=new ContentValues(); values.put(MediaStore.Downloads.DISPLAY_NAME,name); values.put(MediaStore.Downloads.MIME_TYPE,"text/plain");
                    values.put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/拾影"); values.put(MediaStore.Downloads.IS_PENDING,1);
                    textUri=context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
                    if (textUri==null) throw new Exception("正文文件无法创建。");
                    try (OutputStream output=context.getContentResolver().openOutputStream(textUri)) { if (output==null) throw new Exception("正文文件无法写入。"); output.write(body); }
                    ContentValues done=new ContentValues(); done.put(MediaStore.Downloads.IS_PENDING,0); context.getContentResolver().update(textUri,done,null,null);
                    records.put(record(info,-System.currentTimeMillis(),info.title+" · 正文",name,"text/plain").put("localUri",textUri.toString()).put("kind","text").put("verified",true).put("bytes",body.length));
                } else {
                    File dir=new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),"拾影");
                    if (!dir.exists()&&!dir.mkdirs()) throw new Exception("正文保存目录无法创建。");
                    legacyText=new File(dir,name); try (OutputStream output=new FileOutputStream(legacyText)) { output.write(body); }
                    long id=downloads.addCompletedDownload(info.title+" · 正文","拾影 · 笔记正文",false,"text/plain",legacyText.getAbsolutePath(),body.length,true);
                    jobs.add(id); records.put(record(info,id,info.title+" · 正文",name,"text/plain").put("kind","text").put("verified",true).put("bytes",body.length));
                }
            }
            if (info.isImages()) for (int i=0;i<records.length();i++) records.getJSONObject(i).put("albumBatch",albumBatch).put("albumTitle",info.title);
            return records;
        } catch (Exception e) {
            for (long id:jobs) downloads.remove(id);
            if (textUri!=null) context.getContentResolver().delete(textUri,null,null);
            if (legacyText!=null) legacyText.delete();
            throw e;
        }
    }
    static List<Prepared> prepareAudio(VideoResolver resolver,VideoInfo info,VideoInfo.Format selection) throws Exception {
        if (info.isImages()) throw new Exception("图文没有可提取的视频音轨。");
        List<Prepared> list=new ArrayList<>();
        for (VideoInfo.Asset asset:info.selectedAssets(selection)) {
            if ("dash".equals(selection.mode)&&!"audio".equals(asset.kind)) continue;
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
            list.add(new Prepared(asset,resolver.probe(info,asset),selection.mode));
        }
        if (list.isEmpty()) throw new Exception("没有可用的音轨，请选择带声音的画质。"); return list;
    }
    static JSONObject record(VideoInfo info,long id,String title,String file,String mime) throws Exception {
        return new JSONObject().put("id",id).put("title",title).put("author",info.author).put("source",info.sourceUrl)
            .put("file",file).put("mime",mime).put("time",System.currentTimeMillis()).put("verified",false).put("noteId",info.id);
    }
}
