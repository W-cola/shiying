package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.drawable.BitmapDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

/** Real album preview/download plus a separately created owned batch for deletion QA. */
public final class NativeAlbumChecks extends Instrumentation {
    int checks;
    void check(boolean value,String text) { if (!value) throw new AssertionError(text); checks++; }
    <T> T ui(Callable<T> call) throws Exception { FutureTask<T> task=new FutureTask<>(call); runOnMainSync(task); return task.get(); }
    Object field(Object object,String name) throws Exception { java.lang.reflect.Field f=object.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(object); }
    void invoke(MainActivity activity,String name,Class<?> type,Object value) throws Exception { java.lang.reflect.Method m=MainActivity.class.getDeclaredMethod(name,type); m.setAccessible(true); m.invoke(activity,value); }
    TextView text(View v,String value) { if (v instanceof TextView&&value.equals(((TextView)v).getText().toString())) return (TextView)v; if (v instanceof ViewGroup) for (int i=0;i<((ViewGroup)v).getChildCount();i++) { TextView result=text(((ViewGroup)v).getChildAt(i),value); if (result!=null) return result; } return null; }
    JSONObject album(JSONArray records,String batch) throws Exception { JSONArray groups=AlbumRecords.groups(records); for (int i=0;i<groups.length();i++) { JSONObject g=groups.optJSONObject(i); if (AlbumRecords.isAlbum(g)&&g.getJSONArray("items").getJSONObject(0).optString("albumBatch").equals(batch)) return g; } return null; }
    void ready(ImageActivity activity,int number) throws Exception {
        long deadline=System.currentTimeMillis()+50000;
        while (System.currentTimeMillis()<deadline) {
            if (ui(()-> { ImageView image=(ImageView)field(activity,"image"); return image.getDrawable() instanceof BitmapDrawable&&((Integer)field(activity,"index"))==number; })) break;
            Thread.sleep(150);
        }
        ui(()-> { ImageView image=(ImageView)field(activity,"image"); check(image.getDrawable() instanceof BitmapDrawable,"Native image decoded: "+number); Bitmap bitmap=((BitmapDrawable)image.getDrawable()).getBitmap(); check(bitmap.getWidth()>100&&bitmap.getHeight()>100,"Real image dimensions are present"); check(((TextView)field(activity,"count")).getText().toString().equals((number+1)+" / 10"),"Counter follows actual page"); return null; });
    }
    void swipe(ImageActivity activity,boolean left) throws Exception {
        ImageView image=ui(()->(ImageView)field(activity,"image")); ui(()->{ long now=android.os.SystemClock.uptimeMillis(); float y=image.getHeight()/2f,from=image.getWidth()*(left?.8f:.2f),to=image.getWidth()*(left?.2f:.8f); MotionEvent down=MotionEvent.obtain(now,now,0,from,y,0),up=MotionEvent.obtain(now,now+200,1,to,y,0); image.dispatchTouchEvent(down); image.dispatchTouchEvent(up); down.recycle(); up.recycle(); return null; });
    }
    void tapDialog(String value) throws Exception {
        android.view.accessibility.AccessibilityNodeInfo control=null; long deadline=System.currentTimeMillis()+6000;
        while (control==null&&System.currentTimeMillis()<deadline) {
            android.view.accessibility.AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
            if (root!=null) { java.util.List<android.view.accessibility.AccessibilityNodeInfo> found=root.findAccessibilityNodeInfosByText(value); if (!found.isEmpty()) control=found.get(0); }
            if (control==null) Thread.sleep(100);
        }
        check(control!=null,"Collection confirmation offers "+value); android.graphics.Rect bounds=new android.graphics.Rect(); control.getBoundsInScreen(bounds); long now=android.os.SystemClock.uptimeMillis();
        sendPointerSync(MotionEvent.obtain(now,now,0,bounds.centerX(),bounds.centerY(),0)); sendPointerSync(MotionEvent.obtain(now,now+80,1,bounds.centerX(),bounds.centerY(),0));
    }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            JSONArray old=RecordStore.read(context); Set<Long> oldIds=new HashSet<>(); for (int i=0;i<old.length();i++) oldIds.add(old.getJSONObject(i).getLong("id"));
            JSONArray oldGroups=AlbumRecords.groups(old); int legacy=0;
            for (int i=0;i<oldGroups.length();i++) if (AlbumRecords.isAlbum(oldGroups.getJSONObject(i))) legacy++;
            check(legacy>0&&oldGroups.length()<old.length(),"Existing flat photo history is grouped without re-downloading");
            MainActivity main=(MainActivity)startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            VideoResolver resolver=new VideoResolver(url->android.webkit.CookieManager.getInstance().getCookie(url),s->{});
            VideoInfo info=resolver.resolve("https://v.kuaishou.com/njS1JbGL"); check(info.isImages()&&info.imageCount()==10,"Real supplied Kuaishou album contains ten ordered images");
            ui(()->{ invoke(main,"setVideo",VideoInfo.class,info); return null; });
            ActivityMonitor monitor=addMonitor(ImageActivity.class.getName(),null,false);
            ui(()->{ TextView button=text(main.getWindow().getDecorView(),"▧  应用内预览"); check(button!=null,"Parsed album offers native preview"); button.performClick(); return null; });
            ImageActivity remote=(ImageActivity)waitForMonitorWithTimeout(monitor,6000); removeMonitor(monitor); check(remote!=null,"Online album stays inside APK");
            ready(remote,0); swipe(remote,true); ready(remote,1); swipe(remote,false); ready(remote,0);
            check(RecordStore.read(context).length()==old.length(),"Online preview creates no download history");
            runOnMainSync(remote::finish); Thread.sleep(600);
            java.lang.reflect.Method save=MainActivity.class.getDeclaredMethod("startDownload"); save.setAccessible(true); runOnMainSync(()->{ try { save.invoke(main); } catch (Exception e) { throw new RuntimeException(e); } });
            long deadline=System.currentTimeMillis()+120000; String batch=""; JSONObject collection=null;
            while (System.currentTimeMillis()<deadline) {
                JSONArray current=RecordStore.read(context);
                for (int i=0;i<current.length();i++) { JSONObject r=current.getJSONObject(i); if (!oldIds.contains(r.getLong("id"))&&!r.optString("albumBatch").isEmpty()) batch=r.optString("albumBatch"); }
                if (!batch.isEmpty()) { collection=album(current,batch); if (collection!=null) {
                    int completed=0; JSONArray images=AlbumRecords.images(collection);
                    for (int i=0;i<images.length();i++) { long id=images.getJSONObject(i).getLong("id"); if (!context.getSharedPreferences("gallery",0).getString("uri_"+id,"").isEmpty()) completed++; }
                    if (completed==10) break;
                } }
                Thread.sleep(200);
            }
            check(collection!=null&&collection.optInt("imageCount")==10,"New download is one visible ten-image collection");
            check(collection.getJSONArray("items").length()==11&&AlbumRecords.text(collection)!=null,"All images and caption belong to same batch");
            JSONArray downloaded=AlbumRecords.images(collection); long bytes=0;
            for (int i=0;i<downloaded.length();i++) {
                JSONObject image=downloaded.getJSONObject(i); long id=image.getLong("id"); Uri gallery=Uri.parse(context.getSharedPreferences("gallery",0).getString("uri_"+id,""));
                try (Cursor c=context.getContentResolver().query(gallery,new String[]{"relative_path","is_pending","_size"},null,null,null)) { check(c!=null&&c.moveToFirst()&&c.getString(0).equals("Pictures/拾影/")&&c.getInt(1)==0,"Each original photo remains in the system gallery"); bytes+=c.getLong(2); }
            }
            final JSONObject saved=collection; monitor=addMonitor(ImageActivity.class.getName(),null,false);
            ui(()->{ invoke(main,"showRecord",JSONObject.class,saved); return null; });
            ImageActivity local=(ImageActivity)waitForMonitorWithTimeout(monitor,6000); removeMonitor(monitor); check(local!=null,"Collection row opens the in-app swipe gallery directly");
            ready(local,0); swipe(local,true); ready(local,1); swipe(local,false); ready(local,0);
            ui(()->{ ((TextView)field(local,"previous")).performClick(); check(((Integer)field(local,"index"))==0,"First page cannot swipe before beginning"); return null; });
            runOnMainSync(local::finish); Thread.sleep(600);
            ui(()->{ invoke(main,"switchTab",int.class,1); ViewGroup rows=(ViewGroup)field(main,"libraryRows"); check(rows.getChildCount()==AlbumRecords.groups(RecordStore.read(context)).length(),"Library has one row per collection rather than per photo");
                View control=main.getWindow().getDecorView().findViewWithTag(saved.getLong("id")); check(control!=null&&control.isEnabled(),"Collection has one enabled delete button"); control.performClick(); return null; });
            tapDialog("保留"); Thread.sleep(250); check(album(RecordStore.read(context),batch)!=null,"Cancelling whole-collection delete preserves its files and record");
            ui(()->{ main.getWindow().getDecorView().findViewWithTag(saved.getLong("id")).performClick(); return null; });
            tapDialog("删除文件");
            deadline=System.currentTimeMillis()+20000;
            while (System.currentTimeMillis()<deadline&&album(RecordStore.read(context),batch)!=null) Thread.sleep(150);
            check(album(RecordStore.read(context),batch)==null,"Whole collection removed from history");
            for (int i=0;i<downloaded.length();i++) {
                long id=downloaded.getJSONObject(i).getLong("id"); check(manager.getUriForDownloadedFile(id)==null,"Deleting collection removes every owned image download");
                check(context.getSharedPreferences("gallery",0).getBoolean("removed_"+id,false),"Deleted picture has persistent tombstone");
            }
            JSONObject caption=AlbumRecords.text(saved); try (InputStreamProbe ignored=new InputStreamProbe(context,Uri.parse(caption.optString("localUri")))) { throw new AssertionError("Caption survived collection deletion"); } catch (java.io.FileNotFoundException expected) { checks++; }
            Set<Long> remaining=new HashSet<>(); JSONArray current=RecordStore.read(context); for (int i=0;i<current.length();i++) remaining.add(current.getJSONObject(i).getLong("id")); check(remaining.equals(oldIds),"Deleting this test collection preserves every previous file record");
            JSONArray stale=new JSONArray(); for (int i=0;i<saved.getJSONArray("items").length();i++) stale.put(saved.getJSONArray("items").get(i)); for (int i=0;i<current.length();i++) stale.put(current.get(i)); RecordStore.save(context,stale); check(RecordStore.read(context).length()==old.length(),"Stale save cannot resurrect deleted collection files");
            report.putString("result","PASS: legacy groups, real ten-image remote/local swipe gallery, one visible download collection, all gallery photos, caption and whole-batch deletion with other records preserved"); report.putInt("checks",checks); report.putInt("images",10); report.putLong("bytes",bytes); report.putInt("legacy_collections",legacy); report.putString("scope","Isolated Android 15 emulator; user's actual Kuaishou image share; deletion only of a newly created test batch"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); report.putInt("checks",checks); finish(Activity.RESULT_CANCELED,report); }
    }
    private static final class InputStreamProbe implements AutoCloseable {
        final java.io.InputStream stream; InputStreamProbe(Context context,Uri uri) throws Exception { stream=context.getContentResolver().openInputStream(uri); }
        public void close() throws Exception { if (stream!=null) stream.close(); }
    }
}
