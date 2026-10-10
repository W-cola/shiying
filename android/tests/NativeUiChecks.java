package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.EditText;
import cn.shiying.mobile.core.VideoInfo;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.concurrent.FutureTask;

/** Runs only on the project's isolated emulator, using actual owned downloads. */
public final class NativeUiChecks extends Instrumentation {
    int checks;
    void check(boolean value,String message) { if (!value) throw new AssertionError(message); checks++; }
    Object field(Activity activity,String name) throws Exception {
        java.lang.reflect.Field field=activity.getClass().getDeclaredField(name); field.setAccessible(true); return field.get(activity);
    }
    void field(Activity activity,String name,Object value) throws Exception {
        java.lang.reflect.Field field=activity.getClass().getDeclaredField(name); field.setAccessible(true); field.set(activity,value);
    }
    void invoke(Activity activity,String name,Class<?> type,Object value) throws Exception {
        java.lang.reflect.Method method=activity.getClass().getDeclaredMethod(name,type); method.setAccessible(true); method.invoke(activity,value);
    }
    boolean exists(Context context,Uri uri) throws Exception {
        try (InputStream input=context.getContentResolver().openInputStream(uri)) { return input!=null; }
        catch (java.io.FileNotFoundException e) { return false; }
    }
    void deleteViaButton(Activity activity,long id,boolean confirm) throws Exception {
        runOnMainSync(()-> {
            View control=activity.getWindow().getDecorView().findViewWithTag(Long.valueOf(id));
            check(control!=null&&control.isEnabled(),"Every library row has an enabled delete control"); control.performClick();
        });
        waitForIdleSync();
        String label=confirm?"删除文件":"保留";
        java.util.List<AccessibilityNodeInfo> buttons=new ArrayList<>(); long uiDeadline=System.currentTimeMillis()+6000;
        while (buttons.isEmpty()&&System.currentTimeMillis()<uiDeadline) {
            AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
            if (root!=null) buttons=root.findAccessibilityNodeInfosByText(label);
            if (buttons.isEmpty()) Thread.sleep(100);
        }
        check(!buttons.isEmpty(),"Delete confirmation offers "+label);
        check(buttons.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK),"Confirmation click accepted");
        if (confirm) {
            long deadline=System.currentTimeMillis()+12000;
            while (System.currentTimeMillis()<deadline) {
                JSONArray records=RecordStore.read(getTargetContext()); boolean found=false;
                for (int i=0;i<records.length();i++) if (records.getJSONObject(i).optLong("id")==id) found=true;
                if (!found) break; Thread.sleep(150);
            }
            JSONArray records=RecordStore.read(getTargetContext());
            for (int i=0;i<records.length();i++) check(records.getJSONObject(i).optLong("id")!=id,"Deleted record is absent from persistent history");
        }
        waitForIdleSync();
    }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            JSONArray original=RecordStore.read(context); Uri copyFrom=null;
            for (int i=0;i<original.length();i++) {
                JSONObject record=original.getJSONObject(i); if (!record.optString("mime","video/mp4").startsWith("video/")) continue;
                try (Cursor c=manager.query(new DownloadManager.Query().setFilterById(record.optLong("id")))) {
                    if (c==null||!c.moveToFirst()||c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))!=DownloadManager.STATUS_SUCCESSFUL) continue;
                    String local=c.getString(c.getColumnIndexOrThrow(DownloadManager.COLUMN_LOCAL_URI));
                    if (local==null||!Uri.parse(local).getPath().endsWith(record.getString("file"))) continue;
                    Uri uri=manager.getUriForDownloadedFile(record.getLong("id")); if (uri==null||!exists(context,uri)) continue;
                    copyFrom=uri; break;
                }
            }
            check(copyFrom!=null,"An existing app-owned MP4 is available as the local test sample");
            String filename="UI-删除视频验证-"+System.currentTimeMillis()+".mp4";
            ContentValues sample=new ContentValues(); sample.put(MediaStore.Downloads.DISPLAY_NAME,filename); sample.put(MediaStore.Downloads.MIME_TYPE,"video/mp4"); sample.put(MediaStore.Downloads.RELATIVE_PATH,"Download/拾影"); sample.put(MediaStore.Downloads.IS_PENDING,1);
            Uri gallery=context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,sample); long bytes=0;
            try (InputStream input=context.getContentResolver().openInputStream(copyFrom);OutputStream output=context.getContentResolver().openOutputStream(gallery)) {
                byte[] buffer=new byte[8192]; int n; while ((n=input.read(buffer))>0) { output.write(buffer,0,n); bytes+=n; }
            }
            ContentValues ready=new ContentValues(); ready.put(MediaStore.Video.Media.IS_PENDING,0); context.getContentResolver().update(gallery,ready,null,null);
            String path;
            try (Cursor cursor=context.getContentResolver().query(gallery,new String[]{MediaStore.Video.Media.DATA},null,null,null)) { check(cursor!=null&&cursor.moveToFirst(),"Copied MP4 has a real public video path"); path=cursor.getString(0); }
            long sampleId=manager.addCompletedDownload("UI 删除视频验证","Local QA file",false,"video/mp4",path,bytes,true);
            Uri downloaded=manager.getUriForDownloadedFile(sampleId); check(downloaded!=null&&exists(context,downloaded),"Test copy is an owned DownloadManager file");
            JSONObject target=new JSONObject().put("id",sampleId).put("title","UI 删除视频验证").put("mime","video/mp4").put("directory","Download").put("file",filename).put("verified",true);
            original.put(target); RecordStore.save(context,original); context.getSharedPreferences("gallery",0).edit().putString("uri_"+sampleId,gallery.toString()).commit();
            final Activity activity=startActivitySync(new Intent().setClassName(context,"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            final FutureTask<Void> pending=new FutureTask<>(()->null);
            runOnMainSync(()-> {
                try {
                    EditText input=(EditText)field(activity,"input"); input.setText("https://v.douyin.com/xP--46iFdBs/");
                    VideoInfo info=new VideoInfo(); info.id="123"; info.title="待清空结果"; info.formats.add(new VideoInfo.Format("https://example.org/v.mp4","测试",0,0,0));
                    invoke(activity,"setVideo",VideoInfo.class,info); field(activity,"request",pending); field(activity,"loading",true);
                    ArrayList<View> matches=new ArrayList<>(); activity.getWindow().getDecorView().findViewsWithText(matches,"清空",View.FIND_VIEWS_WITH_TEXT);
                    check(!matches.isEmpty(),"Visible clear button exists"); matches.get(0).performClick();
                    check(input.length()==0&&field(activity,"video")==null,"Clear empties link and parsed result");
                    check(((View)field(activity,"result")).getVisibility()==View.GONE,"Old result is hidden");
                    check(pending.isCancelled()&&!((Boolean)field(activity,"loading")),"Clear cancels pending parse");
                    check(!activity.getIntent().hasExtra(Intent.EXTRA_TEXT),"Cleared share is not restored by its intent");
                    invoke(activity,"switchTab",int.class,1);
                } catch (Exception e) { throw new RuntimeException(e); }
            });
            check(RecordStore.read(context).length()==original.length(),"Clear preserves download history");
            long id=target.getLong("id"); deleteViaButton(activity,id,false);
            check(exists(context,downloaded),"Cancelling deletion preserves the actual video");
            deleteViaButton(activity,id,true);
            check(manager.getUriForDownloadedFile(id)==null,"DownloadManager record removed");
            check(!new java.io.File(path).exists(),"Actual MP4 file removed");
            if (gallery!=null) {
                long mediaId=android.content.ContentUris.parseId(gallery);
                try (android.os.ParcelFileDescriptor descriptor=getUiAutomation().executeShellCommand("content query --uri content://media/external/video/media --where _id="+mediaId);
                     InputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor)) {
                    java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream(); byte[] buffer=new byte[1024]; int n;
                    while ((n=input.read(buffer))>0) output.write(buffer,0,n);
                    check(new String(output.toByteArray(),StandardCharsets.UTF_8).contains("No result found"),"Gallery media entry removed");
                }
            }
            check(RecordStore.read(context).length()==original.length()-1,"Only the chosen history row removed");
            RecordStore.save(context,original); check(RecordStore.read(context).length()==original.length()-1,"A stale activity save cannot resurrect deleted history");
            ContentValues values=new ContentValues(); values.put(MediaStore.Downloads.DISPLAY_NAME,"UI-删除正文测试.txt"); values.put(MediaStore.Downloads.MIME_TYPE,"text/plain"); values.put(MediaStore.Downloads.RELATIVE_PATH,"Download/拾影");
            Uri text=context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
            try (OutputStream output=context.getContentResolver().openOutputStream(text)) { output.write("中文正文".getBytes(StandardCharsets.UTF_8)); }
            JSONObject textRecord=new JSONObject().put("id",-System.currentTimeMillis()).put("title","UI 删除正文测试").put("localUri",text.toString()).put("mime","text/plain").put("bytes",12).put("verified",true);
            runOnMainSync(()-> {
                try { JSONArray all=(JSONArray)field(activity,"records"); all.put(textRecord); RecordStore.save(context,all); invoke(activity,"switchTab",int.class,1); }
                catch (Exception e) { throw new RuntimeException(e); }
            });
            deleteViaButton(activity,textRecord.getLong("id"),true); check(!exists(context,text),"Exported caption file also removed");
            String queuedName="UI-取消任务-"+System.currentTimeMillis()+".mp4";
            DownloadManager.Request queuedRequest=new DownloadManager.Request(Uri.parse("https://example.invalid/shiying-queued-test.mp4"));
            queuedRequest.setTitle("UI 取消任务测试"); queuedRequest.setMimeType("video/mp4");
            queuedRequest.setDestinationInExternalPublicDir("Movies",Uri.encode("拾影/"+queuedName,"/"));
            long queuedId=manager.enqueue(queuedRequest);
            JSONObject queuedRecord=new JSONObject().put("id",queuedId).put("title","UI 取消任务测试").put("mime","video/mp4").put("directory","Movies").put("file",queuedName);
            runOnMainSync(()-> {
                try { JSONArray all=(JSONArray)field(activity,"records"); all.put(queuedRecord); RecordStore.save(context,all); invoke(activity,"switchTab",int.class,1); }
                catch (Exception e) { throw new RuntimeException(e); }
            });
            deleteViaButton(activity,queuedId,true);
            try (Cursor cursor=manager.query(new DownloadManager.Query().setFilterById(queuedId))) { check(cursor==null||!cursor.moveToFirst(),"Deleting an unfinished transfer cancels the system task"); }
            check(RecordStore.read(context).length()==original.length()-1,"Pending-task deletion preserves neighboring records");
            // Completed native assembly records use MediaStore directly rather than a DM parent.
            ContentValues combinedValues=new ContentValues(); String combinedName="UI-合并视频删除-"+System.currentTimeMillis()+".mp4";
            combinedValues.put(MediaStore.Video.Media.DISPLAY_NAME,combinedName); combinedValues.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4"); combinedValues.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/拾影");
            Uri combined=context.getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,combinedValues);
            try (InputStream input=context.getContentResolver().openInputStream(copyFrom);OutputStream output=context.getContentResolver().openOutputStream(combined)) { byte[] buffer=new byte[8192]; int n; while ((n=input.read(buffer))>0) output.write(buffer,0,n); }
            String combinedPath; try (Cursor cursor=context.getContentResolver().query(combined,new String[]{"_data"},null,null,null)) { check(cursor!=null&&cursor.moveToFirst(),"Combined video has a real file path"); combinedPath=cursor.getString(0); }
            long combinedId=4000000000000000L+System.currentTimeMillis(); android.content.SharedPreferences jobs=context.getSharedPreferences("compound",0); int serial=jobs.getInt("serial",100000)+1; jobs.edit().putInt("serial",serial).commit();
            JSONObject combinedJob=new JSONObject().put("state","done").put("schedulerId",serial).put("localUri",combined.toString()).put("outputUri",combined.toString()).put("bytes",bytes).put("parts",new JSONArray()); CompoundDownloads.put(context,combinedId,combinedJob);
            JSONObject combinedRecord=new JSONObject().put("id",combinedId).put("title","UI 合并视频删除测试").put("mime","video/mp4").put("file",combinedName).put("compound",true).put("directory","Movies");
            runOnMainSync(()-> { try { JSONArray all=(JSONArray)field(activity,"records"); all.put(combinedRecord); RecordStore.save(context,all); invoke(activity,"switchTab",int.class,1); } catch (Exception e) { throw new RuntimeException(e); } });
            deleteViaButton(activity,combinedId,false); check(exists(context,combined),"Cancel preserves an assembled video");
            deleteViaButton(activity,combinedId,true); check(!exists(context,combined)&&!new java.io.File(combinedPath).exists(),"Compound deletion removes the actual MP4 and gallery row");
            long activeId=combinedId+1; int activeSerial=serial+1; jobs.edit().putInt("serial",activeSerial).commit();
            DownloadManager.Request partRequest=new DownloadManager.Request(Uri.parse("https://example.invalid/shiying-compound-cancel.mp4")); partRequest.setDestinationInExternalFilesDir(context,"media-parts","UI-queued-part.mp4"); long child=manager.enqueue(partRequest);
            java.io.File pendingCache=new java.io.File(context.getCacheDir(),"assembled_"+activeId+".mp4"); try (OutputStream output=new java.io.FileOutputStream(pendingCache)) { output.write(new byte[]{1,2,3}); }
            CompoundDownloads.put(context,activeId,new JSONObject().put("state","downloading").put("schedulerId",activeSerial).put("expected",1).put("decodeKey","123456789").put("cache",pendingCache.getPath()).put("parts",new JSONArray().put(new JSONObject().put("id",child))));
            JSONObject activeRecord=new JSONObject().put("id",activeId).put("title","UI 合并下载取消测试").put("mime","video/mp4").put("compound",true).put("file","UI-queued.mp4").put("directory","Movies");
            runOnMainSync(()-> { try { JSONArray all=(JSONArray)field(activity,"records"); all.put(activeRecord); RecordStore.save(context,all); invoke(activity,"switchTab",int.class,1); } catch (Exception e) { throw new RuntimeException(e); } });
            deleteViaButton(activity,activeId,true);
            try (Cursor cursor=manager.query(new DownloadManager.Query().setFilterById(child))) { check(cursor==null||!cursor.moveToFirst(),"Deleting active assembly cancels its owned child transfer"); }
            check(!pendingCache.exists(),"Deleting active assembly removes its temporary file"); check(!CompoundDownloads.job(context,activeId).has("decodeKey"),"Cancelled playback key is cleared");
            check(RecordStore.read(context).length()==original.length()-1,"Compound deletion preserves all other history");
            Drawable icon=context.getPackageManager().getApplicationIcon(context.getPackageName()); Bitmap bitmap=Bitmap.createBitmap(512,512,Bitmap.Config.ARGB_8888);
            icon.setBounds(0,0,512,512); icon.draw(new Canvas(bitmap));
            ContentValues preview=new ContentValues(); preview.put(MediaStore.Images.Media.DISPLAY_NAME,"shiying-icon-v1.3.png"); preview.put(MediaStore.Images.Media.MIME_TYPE,"image/png"); preview.put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/ShiYing-QA");
            Uri image=context.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,preview);
            try (OutputStream output=context.getContentResolver().openOutputStream(image)) { bitmap.compress(Bitmap.CompressFormat.PNG,100,output); }
            report.putString("result","PASS: clear UI, parse cancellation, delete cancellation, actual MP4/file/gallery deletion, caption deletion, pending-transfer cancellation, completed compound video deletion, active compound transfer/cache cancellation, neighboring records and stale-save protection");
            report.putInt("checks",checks); report.putString("icon_preview","/sdcard/Pictures/ShiYing-QA/shiying-icon-v1.3.png");
            report.putString("scope","isolated emulator and app-owned test files only"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,report); }
    }
}
