package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.Intent;
import android.database.Cursor;
import android.os.Bundle;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/** Installed only on the isolated QA emulator, never included in the delivered app. */
public final class NativeMediaChecks extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            String id=String.format(java.util.Locale.ROOT,"%024x",System.currentTimeMillis());
            JSONObject note=new JSONObject().put("noteId",id).put("type","normal").put("title","# 图文保存验证 100%（测试样本）")
                .put("desc","中文正文第一行\n第二行 undefined 和表情 😀").put("user",new JSONObject().put("nickname","测试"))
                .put("imageList",new JSONArray().put(new JSONObject().put("urlDefault","https://www.gstatic.com/webp/gallery/1.jpg").put("width",550).put("height",368))
                    .put(new JSONObject().put("urlDefault","https://www.gstatic.com/webp/gallery/1.webp").put("width",550).put("height",368)));
            String source="https://www.xiaohongshu.com/explore/"+id+"?xsec_token=AB_fixture";
            VideoInfo info=VideoResolver.fromPayload(note,id,source,source);
            if (info==null||info.imageCount()!=2) throw new AssertionError("Native album parsing failed");
            DownloadManager downloads=(DownloadManager)getTargetContext().getSystemService("download");
            final Activity activity=startActivitySync(new Intent().setClassName(getTargetContext(),"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            final JSONArray[] created={null};
            final JSONArray[] previous={null};
            runOnMainSync(()-> {
                try {
                    java.lang.reflect.Field records=activity.getClass().getDeclaredField("records"); records.setAccessible(true);
                    previous[0]=new JSONArray(((JSONArray)records.get(activity)).toString());
                    java.lang.reflect.Method bind=activity.getClass().getDeclaredMethod("setVideo",VideoInfo.class); bind.setAccessible(true); bind.invoke(activity,info);
                    java.lang.reflect.Method save=activity.getClass().getDeclaredMethod("startDownload"); save.setAccessible(true); save.invoke(activity);
                } catch (Exception e) { throw new RuntimeException(e); }
            });
            long deadline=System.currentTimeMillis()+45000;
            while (created[0]==null&&System.currentTimeMillis()<deadline) {
                runOnMainSync(()-> {
                    try {
                        java.lang.reflect.Field field=activity.getClass().getDeclaredField("records"); field.setAccessible(true);
                        JSONArray all=(JSONArray)field.get(activity),newRecords=new JSONArray();
                        for (int i=0;i<all.length();i++) if (id.equals(all.getJSONObject(i).optString("noteId"))) newRecords.put(all.get(i));
                        if (newRecords.length()==3) created[0]=newRecords;
                    } catch (Exception e) { throw new RuntimeException(e); }
                });
                if (created[0]==null) Thread.sleep(300);
            }
            if (created[0]==null) throw new AssertionError("The existing save button did not schedule the album");
            if (created[0].length()!=3) throw new AssertionError("Expected two photos and caption document");
            for (int i=0;i<2;i++) {
                long job=created[0].getJSONObject(i).getLong("id"); boolean done=false;
                while (System.currentTimeMillis()<deadline) {
                    try (Cursor c=downloads.query(new DownloadManager.Query().setFilterById(job))) {
                        if (c!=null&&c.moveToFirst()) {
                            int state=c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                            if (state==DownloadManager.STATUS_SUCCESSFUL) {
                                android.net.Uri location=android.net.Uri.parse(c.getString(c.getColumnIndexOrThrow(DownloadManager.COLUMN_LOCAL_URI)));
                                if (location.getFragment()!=null||!location.getPath().endsWith(created[0].getJSONObject(i).getString("file"))) throw new AssertionError("Hashtags or percent signs truncated the media filename");
                                done=true; break;
                            }
                            if (state==DownloadManager.STATUS_FAILED) throw new AssertionError("Image download failed: "+c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON)));
                        }
                    }
                    Thread.sleep(300);
                }
                if (!done) throw new AssertionError("Image transfer timed out");
                try (InputStream stream=getTargetContext().getContentResolver().openInputStream(downloads.getUriForDownloadedFile(job))) {
                    byte[] header=new byte[64]; int n=stream.read(header);
                    if (cn.shiying.mobile.core.MediaHeaders.detect(header,n,"image")==null) throw new AssertionError("Bad saved image");
                }
            }
            JSONObject text=created[0].getJSONObject(2);
            for (int i=0;i<2;i++) {
                long imageId=created[0].getJSONObject(i).getLong("id");
                long mediaDeadline=System.currentTimeMillis()+5000; String mediaUri="";
                while (mediaUri.isEmpty()&&System.currentTimeMillis()<mediaDeadline) {
                    MediaPublisher.publish(getTargetContext(),imageId,()->{});
                    mediaUri=getTargetContext().getSharedPreferences("gallery",0).getString("uri_"+imageId,""); if (mediaUri.isEmpty()) Thread.sleep(100);
                }
                if (mediaUri.isEmpty()) throw new AssertionError("Image was not published to gallery");
                try (Cursor c=getTargetContext().getContentResolver().query(android.net.Uri.parse(mediaUri),new String[]{"relative_path","is_pending"},null,null,null)) {
                    if (c==null||!c.moveToFirst()||!"Pictures/拾影/".equals(c.getString(0))||c.getInt(1)!=0) throw new AssertionError("Image is not a completed item in the album folder");
                }
            }
            try (InputStream stream=getTargetContext().getContentResolver().openInputStream(android.net.Uri.parse(text.getString("localUri")))) {
                java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream(); byte[] buffer=new byte[1024]; int n;
                while ((n=stream.read(buffer))>0) bytes.write(buffer,0,n);
                String saved=new String(bytes.toByteArray(),StandardCharsets.UTF_8);
                if (!saved.contains(info.description)||saved.contains("AB_fixture")) throw new AssertionError("Caption export is incomplete or contains signed token");
            }
            JSONArray saved=new JSONArray(getTargetContext().getSharedPreferences("shiying",0).getString("downloads","[]"));
            if (saved.length()!=previous[0].length()+3) throw new AssertionError("New history was not saved");
            for (int i=0;i<previous[0].length();i++) {
                long oldId=previous[0].getJSONObject(i).getLong("id"); boolean retained=false;
                for (int j=0;j<saved.length();j++) if (saved.getJSONObject(j).getLong("id")==oldId) retained=true;
                if (!retained) throw new AssertionError("An existing history record was lost");
            }
            waitForIdleSync();
            result.putString("result","PASS: existing app save flow downloaded two images into Pictures/拾影, both visible in MediaStore gallery, exported UTF8 caption and retained history");
            result.putString("fixture","synthetic note with official Google WebP sample images; distinct from the user's real notes");
            finish(Activity.RESULT_OK,result);
        } catch (Throwable e) { result.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,result); }
    }
}
