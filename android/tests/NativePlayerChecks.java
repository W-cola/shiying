package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.database.Cursor;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.VideoView;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

/** Exercise actual Android playback, UI entry points and lifecycle on our emulator. */
public final class NativePlayerChecks extends Instrumentation {
    int checks;
    JSONArray cases=new JSONArray();
    void check(boolean value,String message) { if (!value) throw new AssertionError(message); checks++; }
    Object field(Object object,String name) throws Exception { java.lang.reflect.Field f=object.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(object); }
    <T> T ui(Callable<T> callable) throws Exception { FutureTask<T> task=new FutureTask<>(callable); runOnMainSync(task); return task.get(); }
    TextView text(View root,String label) {
        if (root instanceof TextView&&label.equals(((TextView)root).getText().toString())) return (TextView)root;
        if (root instanceof ViewGroup) for (int i=0;i<((ViewGroup)root).getChildCount();i++) { TextView result=text(((ViewGroup)root).getChildAt(i),label); if (result!=null) return result; } return null;
    }
    void waitReady(PlayerActivity activity,long milliseconds) throws Exception {
        long deadline=System.currentTimeMillis()+milliseconds;
        while (System.currentTimeMillis()<deadline) {
            if (ui(()->(Boolean)field(activity,"ready"))) return;
            String error=ui(()->((TextView)field(activity,"message")).getText().toString());
            if (error.contains("失败")||error.contains("不可用")||error.contains("无效")) throw new AssertionError(error);
            Thread.sleep(150);
        }
        throw new AssertionError("Playback preparation timed out: "+ui(()->((TextView)field(activity,"message")).getText().toString()));
    }
    void verifyTracks(PlayerActivity activity,String platform) throws Exception {
        JSONObject value=ui(()->{
            MediaPlayer media=(MediaPlayer)field(activity,"media"); boolean video=false,audio=false;
            for (MediaPlayer.TrackInfo track:media.getTrackInfo()) { video|=track.getTrackType()==MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_VIDEO; audio|=track.getTrackType()==MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_AUDIO; }
            VideoView view=(VideoView)field(activity,"videoView");
            check(video&&audio,"Actual playback has both picture and sound: "+platform);
            check(media.getVideoWidth()>0&&media.getVideoHeight()>0&&view.getDuration()>1000,"Real decoded video dimensions and duration: "+platform);
            return new JSONObject().put("platform",platform).put("width",media.getVideoWidth()).put("height",media.getVideoHeight()).put("duration_ms",view.getDuration()).put("audio",audio);
        });
        int begin=ui(()->((VideoView)field(activity,"videoView")).getCurrentPosition()),after=begin;
        long decodeDeadline=System.currentTimeMillis()+8000;
        while (after<begin+200&&System.currentTimeMillis()<decodeDeadline) {
            Thread.sleep(150); after=ui(()->((VideoView)field(activity,"videoView")).getCurrentPosition());
        }
        check(after>begin+200,"Native playback clock advances: "+platform); cases.put(value);
    }
    int galleryCount(Context context) { try (Cursor c=context.getContentResolver().query(android.provider.MediaStore.Video.Media.EXTERNAL_CONTENT_URI,new String[]{"_id"},null,null,null)) { return c==null?0:c.getCount(); } }
    void close(PlayerActivity activity) throws Exception {
        PlayerSource session=ui(()->(PlayerSource)field(activity,"source"));
        File folder=session==null?null:(File)field(session,"directory"); runOnMainSync(activity::finish);
        long deadline=System.currentTimeMillis()+5000;
        while (System.currentTimeMillis()<deadline&&!ui(()->(Boolean)field(activity,"destroyed"))) Thread.sleep(100);
        check(ui(()->(Boolean)field(activity,"destroyed")),"Player releases resources after activity closes");
        if (folder!=null) check(!folder.exists(),"Playback cache removed after leaving player");
    }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); DownloadManager downloads=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            int history=RecordStore.read(context).length(),gallery=galleryCount(context); JSONArray records=RecordStore.read(context); JSONObject sample=null;
            for (int i=0;i<records.length();i++) {
                JSONObject r=records.getJSONObject(i); if (!r.optString("mime").startsWith("video/")||!r.optString("title").contains("Rick")||!r.optString("appError").isEmpty()) continue;
                Uri uri=r.optString("localUri").isEmpty()?downloads.getUriForDownloadedFile(r.optLong("id")):Uri.parse(r.optString("localUri"));
                if (uri==null) continue;
                try (java.io.InputStream input=context.getContentResolver().openInputStream(uri)) { if (input!=null) { sample=r; break; } } catch (Exception ignored) { }
            }
            check(sample!=null,"Existing app-owned Bili download is available for local playback");
            final JSONObject saved=sample;
            MainActivity main=(MainActivity)startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            ActivityMonitor monitor=addMonitor(PlayerActivity.class.getName(),null,false);
            ui(()-> { java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod("showRecord",JSONObject.class); method.setAccessible(true); method.invoke(main,saved); return null; });
            java.util.List<android.view.accessibility.AccessibilityNodeInfo> choices=new java.util.ArrayList<>();
            long choiceDeadline=System.currentTimeMillis()+6000;
            while (choices.isEmpty()&&System.currentTimeMillis()<choiceDeadline) {
                android.view.accessibility.AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
                if (root!=null) choices=root.findAccessibilityNodeInfosByText("播放视频");
                if (choices.isEmpty()) Thread.sleep(100);
            }
            report.putString("library_sample",saved.optString("file")+" "+saved.optString("appError"));
            check(!choices.isEmpty(),"Library dialog offers play action");
            android.graphics.Rect bounds=new android.graphics.Rect(); choices.get(0).getBoundsInScreen(bounds);
            long clickTime=android.os.SystemClock.uptimeMillis();
            sendPointerSync(MotionEvent.obtain(clickTime,clickTime,MotionEvent.ACTION_DOWN,bounds.centerX(),bounds.centerY(),0));
            sendPointerSync(MotionEvent.obtain(clickTime,clickTime+80,MotionEvent.ACTION_UP,bounds.centerX(),bounds.centerY(),0));
            PlayerActivity local=(PlayerActivity)waitForMonitorWithTimeout(monitor,6000); removeMonitor(monitor); check(local!=null,"Library video does not launch an external player");
            waitReady(local,20000); verifyTracks(local,"已下载 B站视频");
            ui(()->{ ((TextView)field(local,"play")).performClick(); return null; });
            int paused=ui(()->((VideoView)field(local,"videoView")).getCurrentPosition()); Thread.sleep(600);
            check(Math.abs(ui(()->((VideoView)field(local,"videoView")).getCurrentPosition())-paused)<150,"Pause holds the playback position");
            ui(()->{
                SeekBar bar=(SeekBar)field(local,"seek"); long now=android.os.SystemClock.uptimeMillis();
                float x=bar.getWidth()*.60f,y=bar.getHeight()/2f;
                MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0),up=MotionEvent.obtain(now,now+80,MotionEvent.ACTION_UP,x,y,0);
                bar.dispatchTouchEvent(down); bar.dispatchTouchEvent(up); down.recycle(); up.recycle(); return null;
            }); Thread.sleep(600);
            check(ui(()->((VideoView)field(local,"videoView")).getCurrentPosition())>60000,"Progress bar seeks into actual video");
            ui(()->{ local.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE); return null; }); Thread.sleep(700);
            check(local.getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE,"Full-screen landscape rotation supported");
            check(ui(()->(Boolean)field(local,"ready")),"Rotation preserves prepared video");
            ui(()->{ local.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT); ((TextView)field(local,"play")).performClick(); return null; }); Thread.sleep(500);
            runOnMainSync(()->callActivityOnPause(local)); Thread.sleep(250);
            check(!ui(()->((VideoView)field(local,"videoView")).isPlaying()),"Player pauses when app goes to background");
            runOnMainSync(()->callActivityOnResume(local)); Thread.sleep(300);
            check(ui(()->((VideoView)field(local,"videoView")).isPlaying()),"Player resumes prior playback when returning"); close(local);
            VideoResolver resolver=new VideoResolver(url->android.webkit.CookieManager.getInstance().getCookie(url),s->{});
            String[][] links={{"抖音","https://v.douyin.com/xP--46iFdBs/"},{"快手","https://v.kuaishou.com/KyQPissP"},{"视频号","https://weixin.qq.com/sph/A3loS34sJs"},{"B站 DASH","https://www.bilibili.com/video/BV1GJ411x7h7"},{"小红书 HEVC","https://www.xiaohongshu.com/discovery/item/6a7bf28a0000000026036ba2?source=webshare&xhsshare=pc_web&xsec_token=AByUzUGbWV8SODDaCU1JL5mJUwlKaJNZcwEqvwBqobUVE=&xsec_source=pc_share"}};
            for (String[] link:links) {
                VideoInfo info=resolver.resolve(link[1]);
                ActivityMonitor playback=addMonitor(PlayerActivity.class.getName(),null,false);
                ui(()->{ java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod("setVideo",VideoInfo.class); method.setAccessible(true); method.invoke(main,info); TextView button=text(main.getWindow().getDecorView(),"▶  应用内播放"); check(button!=null,"Resolved video exposes in-app play button"); button.performClick(); return null; });
                PlayerActivity player=(PlayerActivity)waitForMonitorWithTimeout(playback,6000); removeMonitor(playback); check(player!=null,"Resolved video opened private player: "+link[0]);
                waitReady(player,120000); verifyTracks(player,link[0]); close(player);
                check(RecordStore.read(context).length()==history,"Preview creates no library record: "+link[0]); check(galleryCount(context)==gallery,"Preview creates no gallery file: "+link[0]);
            }
            report.putString("result","PASS: real in-app online/local playback, picture+sound, pause, seek, landscape, lifecycle and no preview gallery/history records");
            report.putInt("checks",checks); report.putString("cases",cases.toString()); report.putString("scope","Isolated Android 15 emulator; actual supplied Douyin/Kuaishou/WeChat links and public Bili DASH; no user phone connected");
            finish(Activity.RESULT_OK,report);
        } catch (Throwable error) { report.putString("error",error.toString()); report.putString("cases",cases.toString()); report.putInt("checks",checks); finish(Activity.RESULT_CANCELED,report); }
    }
}
