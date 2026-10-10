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
import android.widget.EditText;
import android.widget.TextView;
import cn.shiying.mobile.core.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.FutureTask;

/** Real user-supplied public links; operates only on the project's isolated emulator. */
public final class NativeSocialChecks extends Instrumentation {
    void check(boolean value,String message) { if (!value) throw new AssertionError(message); }
    Object field(Activity activity,String name) throws Exception { java.lang.reflect.Field f=activity.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(activity); }
    void call(Activity activity,String name) throws Exception { java.lang.reflect.Method m=activity.getClass().getDeclaredMethod(name); m.setAccessible(true); m.invoke(activity); }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    JSONArray save(Activity activity,VideoInfo info,int expected) throws Exception {
        Context context=getTargetContext(); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
        Set<Long> old=new HashSet<>(); JSONArray before=RecordStore.read(context); for (int i=0;i<before.length();i++) old.add(before.getJSONObject(i).optLong("id"));
        runOnMainSync(()-> { try { java.lang.reflect.Method bind=activity.getClass().getDeclaredMethod("setVideo",VideoInfo.class); bind.setAccessible(true); bind.invoke(activity,info); call(activity,"startDownload"); } catch (Exception e) { throw new RuntimeException(e); } });
        long deadline=System.currentTimeMillis()+180000; JSONArray selected=new JSONArray();
        while (System.currentTimeMillis()<deadline) {
            selected=new JSONArray(); JSONArray current=RecordStore.read(context); boolean ready=true;
            for (int i=0;i<current.length();i++) {
                JSONObject row=current.getJSONObject(i); long id=row.optLong("id"); if (old.contains(id)||!row.optString("noteId").equals(info.id)) continue; selected.put(row);
                if (!row.optString("appError").isEmpty()) throw new AssertionError(row.optString("appError"));
                if (!row.optString("localUri").isEmpty()) continue;
                int state=0; try (Cursor c=manager.query(new DownloadManager.Query().setFilterById(id))) { if (c!=null&&c.moveToFirst()) state=c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)); }
                if (state==DownloadManager.STATUS_FAILED) throw new AssertionError("System media download failed for item "+row.optString("title"));
                if (state!=DownloadManager.STATUS_SUCCESSFUL) ready=false;
                else { MediaPublisher.publish(context,id,()->{}); if (context.getSharedPreferences("gallery",0).getString("uri_"+id,"").isEmpty()) ready=false; }
            }
            if (selected.length()==expected&&ready) return selected; Thread.sleep(250);
        }
        throw new AssertionError("New downloads did not finish before deadline; found "+selected.length());
    }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            Activity activity=startActivitySync(new Intent().setClassName(context,"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            VideoResolver resolver=new VideoResolver(u->android.webkit.CookieManager.getInstance().getCookie(u),s->{});
            VideoInfo video=resolver.resolve("https://v.kuaishou.com/KyQPissP");
            check(video.id.equals("3xvcug35jptf39e")&&!video.isImages()&&video.title.contains("岳父点外卖"),"Exact user-supplied Kuaishou video resolved");
            JSONArray videoRows=save(activity,video,1); JSONObject row=videoRows.getJSONObject(0); long id=row.getLong("id"); Uri videoUri=manager.getUriForDownloadedFile(id);
            MediaExtractor extractor=new MediaExtractor(); boolean picture=false,sound=false; int width=0,height=0;
            try { extractor.setDataSource(context,videoUri,null); for (int i=0;i<extractor.getTrackCount();i++) { android.media.MediaFormat format=extractor.getTrackFormat(i); String mime=format.getString("mime"); if (mime.startsWith("video/")) { picture=true; width=format.getInteger("width"); height=format.getInteger("height"); } if (mime.startsWith("audio/")) sound=true; } } finally { extractor.release(); }
            check(picture&&sound,"Actual Kuaishou MP4 has picture and sound");
            Uri gallery=Uri.parse(context.getSharedPreferences("gallery",0).getString("uri_"+id,"")); String videoPath;
            try (Cursor c=context.getContentResolver().query(gallery,new String[]{"relative_path","is_pending","_data"},null,null,null)) { check(c!=null&&c.moveToFirst()&&c.getString(0).equals("Movies/拾影/")&&c.getInt(1)==0,"Real Kuaishou video published to gallery"); videoPath=c.getString(2); }
            report.putString("video","PASS: user link, actual download, video/audio tracks and public gallery"); report.putString("video_file",videoPath); report.putInt("video_width",width); report.putInt("video_height",height);
            VideoInfo images=resolver.resolve("https://v.kuaishou.com/njS1JbGL");
            check(images.id.equals("3xv5358vvb8eq9k")&&images.isImages()&&images.imageCount()==10&&images.author.equals("Sky治愈风景"),"Exact user-supplied album has 10 images");
            JSONArray imageRows=save(activity,images,11); int imageCount=0,textCount=0; long imageBytes=0;
            for (int i=0;i<imageRows.length();i++) {
                JSONObject item=imageRows.getJSONObject(i); long imageId=item.getLong("id");
                if (item.optString("mime").startsWith("image/")) {
                    imageCount++; Uri imageGallery=Uri.parse(context.getSharedPreferences("gallery",0).getString("uri_"+imageId,""));
                    try (Cursor c=context.getContentResolver().query(imageGallery,new String[]{"relative_path","is_pending","width","height","_size"},null,null,null)) { check(c!=null&&c.moveToFirst()&&c.getString(0).equals("Pictures/拾影/")&&c.getInt(1)==0&&c.getInt(2)==1080&&c.getInt(3)>1000,"Full-resolution image published to public gallery"); imageBytes+=c.getLong(4); }
                    try (InputStream input=context.getContentResolver().openInputStream(manager.getUriForDownloadedFile(imageId))) { android.graphics.Bitmap bitmap=android.graphics.BitmapFactory.decodeStream(input); check(bitmap!=null&&bitmap.getWidth()==1080,"Saved original image decodes"); bitmap.recycle(); }
                } else if (item.optString("mime").equals("text/plain")) {
                    textCount++; try (InputStream input=context.getContentResolver().openInputStream(Uri.parse(item.getString("localUri")))) { java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream(); byte[] buffer=new byte[1024]; int n; while ((n=input.read(buffer))>0) out.write(buffer,0,n); String text=new String(out.toByteArray(),java.nio.charset.StandardCharsets.UTF_8); check(text.contains("Sky治愈风景")&&text.contains("无可替代")&&!text.contains("shareToken"),"Actual UTF8 caption and author saved without share tokens"); }
                }
            }
            check(imageCount==10&&textCount==1,"All 10 images and one caption saved"); report.putString("images","PASS: user link, all 10 original images, 10 public gallery rows and full caption"); report.putInt("image_count",imageCount); report.putLong("image_bytes",imageBytes);
            runOnMainSync(()-> { try { ((EditText)field(activity,"input")).setText("https://weixin.qq.com/sph/AwuKEvusQH"); call(activity,"resolve"); } catch (Exception e) { throw new RuntimeException(e); } });
            VideoInfo wechat=null; long deadline=System.currentTimeMillis()+45000;
            while (System.currentTimeMillis()<deadline) {
                FutureTask<VideoInfo> task=new FutureTask<>(()-> { Object value=field(activity,"video"); return value instanceof VideoInfo?(VideoInfo)value:null; }); runOnMainSync(task); wechat=task.get();
                if (wechat!=null&&wechat.id.equals("AwuKEvusQH")) break; Thread.sleep(250);
            }
            check(wechat!=null&&wechat.id.equals("AwuKEvusQH")&&wechat.author.equals("中国超模"),"Original Sph link resolved via anonymous service in actual UI");
            JSONArray wxRows=save(activity,wechat,1); long wxId=wxRows.getJSONObject(0).getLong("id");
            check(!context.getSharedPreferences("gallery",0).getString("uri_"+wxId,"").isEmpty(),"WeChat video saved into gallery");
            report.putString("wechat","PASS: original share resolved through anonymous service and saved to public gallery");
            report.putString("scope","real supplied links on isolated Android 15; WeChat uses third-party service without user login"); report.putString("result","PASS for Kuaishou video, 10-image download and WeChat video"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,report); }
    }
}
