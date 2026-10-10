package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.media.MediaExtractor;
import android.net.Uri;
import android.os.Bundle;
import cn.shiying.mobile.core.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashSet;
import java.util.Set;

/** Anonymous service + real user link + actual app save on the isolated emulator. */
public final class NativeNoLoginChecks extends Instrumentation {
    void check(boolean value,String message) { if (!value) throw new AssertionError(message); }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            Activity activity=startActivitySync(new Intent().setClassName(context,"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            Set<Long> previous=new HashSet<>(); JSONArray old=RecordStore.read(context); for (int i=0;i<old.length();i++) previous.add(old.getJSONObject(i).optLong("id"));
            // Resolving must not ask the app cookie store for any account or browser session.
            VideoResolver resolver=new VideoResolver(new VideoResolver.Cookies(){ public String get(String url){ throw new AssertionError("Anonymous resolution must not read cookies"); } public void save(String url,String value){ throw new AssertionError("Anonymous resolution must not save service cookies"); }},s->{});
            String source="https://weixin.qq.com/sph/A3loS34sJs"; VideoInfo info=resolver.resolve(source);
            check(info.id.equals("A3loS34sJs")&&info.author.equals("中国超模")&&info.title.contains("冷艳气质"),"Exact supplied WeChat post resolved anonymously");
            check(info.formats.get(0).label.contains("H.264"),"Default format is compatible H264");
            runOnMainSync(()-> { try { java.lang.reflect.Method bind=activity.getClass().getDeclaredMethod("setVideo",VideoInfo.class); bind.setAccessible(true); bind.invoke(activity,info); java.lang.reflect.Method save=activity.getClass().getDeclaredMethod("startDownload"); save.setAccessible(true); save.invoke(activity); } catch (Exception e) { throw new RuntimeException(e); } });
            long deadline=System.currentTimeMillis()+90000; JSONObject row=null; long id=0; Uri gallery=null;
            while (System.currentTimeMillis()<deadline) {
                JSONArray records=RecordStore.read(context);
                for (int i=0;i<records.length();i++) { JSONObject item=records.getJSONObject(i); if (!previous.contains(item.optLong("id"))&&item.optString("noteId").equals(info.id)) { row=item; id=item.getLong("id"); break; } }
                if (row!=null) {
                    if (!row.optString("appError").isEmpty()) throw new AssertionError(row.optString("appError"));
                    int state=0; try (Cursor c=manager.query(new DownloadManager.Query().setFilterById(id))) { if (c!=null&&c.moveToFirst()) state=c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)); }
                    if (state==DownloadManager.STATUS_FAILED) throw new AssertionError("System media transfer failed");
                    if (state==DownloadManager.STATUS_SUCCESSFUL) { MediaPublisher.publish(context,id,()->{}); String uri=context.getSharedPreferences("gallery",0).getString("uri_"+id,""); if (!uri.isEmpty()) { gallery=Uri.parse(uri); break; } }
                } Thread.sleep(250);
            }
            check(gallery!=null,"New completed media published to gallery");
            MediaExtractor extractor=new MediaExtractor(); boolean video=false,audio=false; int width=0,height=0; long duration=0;
            try { extractor.setDataSource(context,manager.getUriForDownloadedFile(id),null); for (int i=0;i<extractor.getTrackCount();i++) { android.media.MediaFormat format=extractor.getTrackFormat(i); String mime=format.getString("mime"); if (mime.startsWith("video/")) { video=true; width=format.getInteger("width"); height=format.getInteger("height"); if (format.containsKey("durationUs")) duration=format.getLong("durationUs"); } audio|=mime.startsWith("audio/"); } } finally { extractor.release(); }
            check(video&&width>0&&height>0&&duration>1000000,"Downloaded file is an actual playable video, not its cover");
            String path=""; long bytes=0;
            try (Cursor c=context.getContentResolver().query(gallery,new String[]{"relative_path","is_pending","_data","_size"},null,null,null)) { check(c!=null&&c.moveToFirst()&&c.getString(0).equals("Movies/拾影/")&&c.getInt(1)==0,"File is visible in the public album"); path=c.getString(2); bytes=c.getLong(3); }
            report.putString("result","PASS: supplied WeChat link resolved without user login or cookie access, actual MP4 downloaded through app, published in public gallery"); report.putString("source",source); report.putString("id",info.id); report.putString("title",info.title); report.putString("author",info.author); report.putString("file",path); report.putInt("width",width); report.putInt("height",height); report.putBoolean("audio",audio); report.putLong("duration_us",duration); report.putLong("bytes",bytes); report.putString("scope","Isolated Android 15 emulator; third-party anonymous API; user's phone and private app data not accessed"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,report); }
    }
}
