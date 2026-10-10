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

/** Actual Bilibili DASH download/mux/gallery verification on the isolated emulator. */
public final class NativePlatformChecks extends Instrumentation {
    void check(boolean value,String name) { if (!value) throw new AssertionError(name); }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext();
            final Activity activity=startActivitySync(new Intent().setClassName(context,"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            java.util.Set<Long> previous=new java.util.HashSet<>(); JSONArray old=RecordStore.read(context); for (int i=0;i<old.length();i++) previous.add(old.getJSONObject(i).optLong("id"));
            VideoResolver resolver=new VideoResolver(u->android.webkit.CookieManager.getInstance().getCookie(u),s->{});
            String source="https://www.bilibili.com/video/BV1GJ411x7h7"; VideoInfo info=resolver.resolve(source);
            check(info.platform.equals("B站"),"The live source is Bilibili");
            check(info.formats.get(0).mode.equals("dash"),"The test selects published separate AVC video and AAC audio");
            final long[] recordId={0};
            runOnMainSync(()-> {
                try {
                    java.lang.reflect.Method bind=activity.getClass().getDeclaredMethod("setVideo",VideoInfo.class); bind.setAccessible(true); bind.invoke(activity,info);
                    java.lang.reflect.Method save=activity.getClass().getDeclaredMethod("startDownload"); save.setAccessible(true); save.invoke(activity);
                } catch (Exception e) { throw new RuntimeException(e); }
            });
            long deadline=System.currentTimeMillis()+180000; JSONObject record=null;
            while (System.currentTimeMillis()<deadline) {
                JSONArray records=RecordStore.read(context);
                for (int i=0;i<records.length();i++) { JSONObject row=records.optJSONObject(i); if (row!=null&&!previous.contains(row.optLong("id"))&&row.optBoolean("compound")&&row.optString("noteId").equals(info.id)) { record=row; recordId[0]=row.optLong("id"); break; } }
                if (record!=null) {
                    long[] stats=new long[3]; int state=CompoundDownloads.query(context,record,stats);
                    if (state==DownloadManager.STATUS_FAILED) throw new AssertionError("Assembly failed: "+CompoundDownloads.job(context,recordId[0]));
                    if (state==DownloadManager.STATUS_SUCCESSFUL) break;
                }
                Thread.sleep(300);
            }
            check(record!=null&&CompoundDownloads.job(context,recordId[0]).optString("state").equals("done"),"Live video finished within test deadline");
            record=CompoundDownloads.decorate(context,record); Uri uri=Uri.parse(record.getString("localUri"));
            MediaExtractor extractor=new MediaExtractor(); boolean video=false,audio=false; int width=0,height=0;
            try {
                extractor.setDataSource(context,uri,null);
                for (int i=0;i<extractor.getTrackCount();i++) { android.media.MediaFormat format=extractor.getTrackFormat(i); String mime=format.getString("mime"); if (mime.startsWith("video/")) { video=true; width=format.getInteger("width"); height=format.getInteger("height"); } if (mime.startsWith("audio/")) audio=true; }
            } finally { extractor.release(); }
            check(video&&audio,"The actual MP4 contains both picture and sound");
            String path="";
            try (Cursor cursor=context.getContentResolver().query(uri,new String[]{"relative_path","is_pending","_data"},null,null,null)) {
                check(cursor!=null&&cursor.moveToFirst(),"Gallery row exists"); check(cursor.getString(0).equals("Movies/拾影/"),"Video saved in the public album folder"); check(cursor.getInt(1)==0,"Video is published to gallery"); path=cursor.getString(2);
            }
            report.putString("result","PASS: live Bilibili source resolved, separate video/audio downloaded by Android, natively muxed into MP4 with both tracks, published in gallery");
            report.putString("source",source); report.putString("id",info.id); report.putString("title",info.title); report.putLong("bytes",record.getLong("bytes")); report.putInt("width",width); report.putInt("height",height); report.putString("file",path);
            report.putString("scope","real public Bilibili example on isolated Android 15 emulator; no third-party parsing service"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,report); }
    }
}
