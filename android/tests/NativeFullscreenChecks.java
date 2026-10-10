package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.VideoView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

/** Actual landscape/portrait local media, immersive insets, controls and Android lifecycle. */
public final class NativeFullscreenChecks extends Instrumentation {
    int checks;
    void check(boolean value,String text) { if (!value) throw new AssertionError(text); checks++; }
    Object field(Object object,String name) throws Exception { java.lang.reflect.Field f=object.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(object); }
    <T> T ui(Callable<T> call) throws Exception { FutureTask<T> task=new FutureTask<>(call); runOnMainSync(task); return task.get(); }
    void invoke(PlayerActivity p,String name,Class<?> type,Object value) throws Exception { java.lang.reflect.Method m=PlayerActivity.class.getDeclaredMethod(name,type); m.setAccessible(true); m.invoke(p,value); }
    void click(PlayerActivity p,String name) throws Exception { ui(()->{ ((View)field(p,name)).performClick(); return null; }); }
    VideoView video(PlayerActivity p) throws Exception { return (VideoView)field(p,"videoView"); }
    void waitReady(PlayerActivity p) throws Exception {
        long end=System.currentTimeMillis()+20000;
        while (System.currentTimeMillis()<end&&!ui(()->(Boolean)field(p,"ready"))) Thread.sleep(100);
        check(ui(()->(Boolean)field(p,"ready")),"Real player prepared successfully: "+ui(()->((TextView)field(p,"message")).getText().toString()));
        Thread.sleep(350);
    }
    void settle(PlayerActivity p,int orientation) throws Exception {
        long end=System.currentTimeMillis()+7000;
        while (System.currentTimeMillis()<end&&p.getResources().getConfiguration().orientation!=orientation) Thread.sleep(100);
        check(p.getResources().getConfiguration().orientation==orientation,"Expected display orientation"); Thread.sleep(500); waitReady(p);
    }
    void pureFullscreen(PlayerActivity p) throws Exception { ui(()->{
        check((Boolean)field(p,"fullscreen"),"Fullscreen state is independent of orientation");
        check(!((Boolean)field(p,"controlsShown")),"Fullscreen hides controls immediately");
        check(((View)field(p,"header")).getVisibility()==View.GONE&&((View)field(p,"controls")).getVisibility()==View.GONE,"Header and all player buttons removed from display");
        View root=(View)field(p,"root"),frame=(View)field(p,"frame"); check(root.getPaddingTop()==0&&root.getPaddingBottom()==0,"Fullscreen does not reserve system-bar padding");
        check(frame.getHeight()==root.getHeight()&&frame.getWidth()==root.getWidth(),"Video container occupies entire window");
        WindowInsets insets=root.getRootWindowInsets(); check(insets!=null&&!insets.isVisible(WindowInsets.Type.statusBars())&&!insets.isVisible(WindowInsets.Type.navigationBars()),"Status and navigation bars are actually hidden");
        return null;
    }); }
    void gesture(PlayerActivity p,float x1,float y1,float x2,float y2) throws Exception { ui(()->{
        View pane=(View)field(p,"touchPane"); long now=android.os.SystemClock.uptimeMillis(); int width=pane.getWidth(),height=pane.getHeight();
        MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x1*width,y1*height,0),move=MotionEvent.obtain(now,now+150,MotionEvent.ACTION_MOVE,x2*width,y2*height,0),up=MotionEvent.obtain(now,now+300,MotionEvent.ACTION_UP,x2*width,y2*height,0);
        pane.dispatchTouchEvent(down); pane.dispatchTouchEvent(move); pane.dispatchTouchEvent(up); down.recycle(); move.recycle(); up.recycle(); return null;
    }); Thread.sleep(450); }
    PlayerActivity open(Context context,JSONObject row) throws Exception {
        DownloadManager dm=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE); Uri uri=row.optString("localUri").isEmpty()?dm.getUriForDownloadedFile(row.getLong("id")):Uri.parse(row.getString("localUri"));
        check(uri!=null,"App-owned downloaded video URI exists");
        PlayerActivity p=(PlayerActivity)startActivitySync(new Intent(context,PlayerActivity.class).putExtra("local",uri.toString()).putExtra("title",row.optString("title")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); waitReady(p); return p;
    }
    void close(PlayerActivity p) throws Exception { runOnMainSync(p::finish); long end=System.currentTimeMillis()+5000; while (System.currentTimeMillis()<end&&!ui(()->(Boolean)field(p,"destroyed"))) Thread.sleep(100); check(ui(()->(Boolean)field(p,"destroyed")),"Playback resources released on exit"); }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); JSONArray rows=RecordStore.read(context); JSONObject wide=null,tall=null;
            DownloadManager downloads=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
            for (int i=0;i<rows.length();i++) {
                JSONObject r=rows.optJSONObject(i); if (!r.optString("mime").startsWith("video/")||!r.optString("appError").isEmpty()) continue;
                Uri uri=r.optString("localUri").isEmpty()?downloads.getUriForDownloadedFile(r.optLong("id")):Uri.parse(r.optString("localUri")); if (uri==null) continue;
                try (java.io.InputStream input=context.getContentResolver().openInputStream(uri)) { if (input==null) continue; } catch (Exception e) { continue; }
                android.media.MediaExtractor extractor=new android.media.MediaExtractor(); boolean portrait=false;
                try { extractor.setDataSource(context,uri,null); for (int t=0;t<extractor.getTrackCount();t++) { android.media.MediaFormat f=extractor.getTrackFormat(t); if (f.getString("mime").startsWith("video/")) portrait=f.getInteger("height")>f.getInteger("width"); } } catch (Exception e) { continue; } finally { extractor.release(); }
                if (wide==null&&r.optString("title").contains("Rick")) wide=r;
                if (portrait&&tall==null) tall=r;
            }
            check(wide!=null&&tall!=null,"Real downloaded horizontal and vertical samples available");
            int oldBrightness=Settings.System.getInt(context.getContentResolver(),Settings.System.SCREEN_BRIGHTNESS,128);
            PlayerActivity p=open(context,wide); final PlayerActivity landscape=p;
            ui(()-> { MediaPlayer m=(MediaPlayer)field(landscape,"media"); check(m.getVideoWidth()>m.getVideoHeight(),"Landscape case has real wide video geometry"); return null; });
            if (ui(()->video(landscape).isPlaying())) click(p,"play");
            ui(()->{ invoke(landscape,"seekTo",int.class,30000); return null; }); Thread.sleep(600);
            int before=ui(()->video(landscape).getCurrentPosition()); check(before>25000,"Starting playback position established");
            click(p,"full"); settle(p,Configuration.ORIENTATION_LANDSCAPE); pureFullscreen(p);
            check(Math.abs(ui(()->video(landscape).getCurrentPosition())-before)<2000,"Entering fullscreen preserves pause position");
            click(p,"touchPane"); check(ui(()->(Boolean)field(landscape,"controlsShown")),"Tap reveals overlay controls in fullscreen");
            check(ui(()->((FrameLayout.LayoutParams)((View)field(landscape,"frame")).getLayoutParams()).bottomMargin)==0,"Overlay controls do not shrink fullscreen picture");
            click(p,"touchPane"); pureFullscreen(p);
            runOnMainSync(p::onBackPressed); settle(p,Configuration.ORIENTATION_PORTRAIT); check(!ui(()->(Boolean)field(landscape,"fullscreen")),"Back exits fullscreen before closing player");
            check(ui(()->((View)field(landscape,"controls")).getVisibility())==View.VISIBLE,"Normal controls return after fullscreen");
            click(p,"rotate"); settle(p,Configuration.ORIENTATION_LANDSCAPE); check(!ui(()->(Boolean)field(landscape,"fullscreen")),"Independent rotate button does not enable fullscreen"); click(p,"rotate"); settle(p,Configuration.ORIENTATION_PORTRAIT);
            ui(()->{ invoke(landscape,"setSpeed",float.class,1.5f); return null; });
            check(!ui(()->video(landscape).isPlaying()),"Changing playback speed does not resume a paused video");
            click(p,"play"); Thread.sleep(200);
            float actualSpeed=ui(()->((MediaPlayer)field(landscape,"media")).getPlaybackParams().getSpeed());
            check(Math.abs(actualSpeed-1.5f)<.01f,"Native engine resumes at actual 1.5x speed: "+actualSpeed+" / selected "+ui(()->field(landscape,"speed")));
            click(p,"play");
            ui(()->{ invoke(landscape,"jump",int.class,15000); return null; }); Thread.sleep(500); check(ui(()->video(landscape).getCurrentPosition())>40000,"Forward fifteen seconds works");
            ui(()->{ invoke(landscape,"jump",int.class,-15000); return null; }); Thread.sleep(500); check(ui(()->video(landscape).getCurrentPosition())<35000,"Backward fifteen seconds works");
            gesture(p,.4f,.5f,.6f,.5f); check(ui(()->video(landscape).getCurrentPosition())>50000,"Horizontal gesture seeks into real media");
            gesture(p,.2f,.6f,.2f,.3f); check(ui(()->(Float)field(landscape,"brightness"))>0,"Left-side vertical gesture changes window brightness");
            gesture(p,.8f,.4f,.8f,.65f); check(ui(()->(Float)field(landscape,"volume"))<.95f,"Right-side vertical gesture changes playback volume");
            ui(()->{ invoke(landscape,"setVolume",float.class,0f); return null; }); check(ui(()->(Float)field(landscape,"volume"))==0,"Mute state supported");
            ui(()->{ invoke(landscape,"setVolume",float.class,.6f); invoke(landscape,"setBrightness",float.class,.35f); invoke(landscape,"setLooping",boolean.class,true); return null; });
            check(ui(()->((MediaPlayer)field(landscape,"media")).isLooping()),"Native looping enabled"); check(Math.abs(p.getWindow().getAttributes().screenBrightness-.35f)<.01f,"Brightness override belongs to player window");
            check(Settings.System.getInt(context.getContentResolver(),Settings.System.SCREEN_BRIGHTNESS,128)==oldBrightness,"Device brightness preference remains unchanged");
            ui(()->{ invoke(landscape,"setSpeed",float.class,1f); invoke(landscape,"seekTo",int.class,video(landscape).getDuration()-300); ((View)field(landscape,"play")).performClick(); return null; });
            long end=System.currentTimeMillis()+8000; while (System.currentTimeMillis()<end&&ui(()->video(landscape).getCurrentPosition())>10000) Thread.sleep(150);
            check(ui(()->video(landscape).isPlaying())&&ui(()->video(landscape).getCurrentPosition())<10000,"Loop actually returns to beginning and continues playing");
            click(p,"full"); settle(p,Configuration.ORIENTATION_LANDSCAPE); click(p,"touchPane"); check(ui(()->(Boolean)field(landscape,"controlsShown")),"Playing fullscreen controls can be revealed"); Thread.sleep(3300); pureFullscreen(p);
            click(p,"touchPane"); click(p,"play"); check(!ui(()->video(landscape).isPlaying()),"Pause action remains reachable inside fullscreen");
            close(p);
            p=open(context,tall); final PlayerActivity portrait=p;
            ui(()->{ invoke(portrait,"setLooping",boolean.class,true); return null; });
            ui(()-> { MediaPlayer m=(MediaPlayer)field(portrait,"media"); check(m.getVideoHeight()>m.getVideoWidth(),"Portrait case has real tall video geometry"); return null; });
            click(p,"full"); settle(p,Configuration.ORIENTATION_PORTRAIT); pureFullscreen(p);
            int begin=ui(()->video(portrait).getCurrentPosition()); Thread.sleep(500); check(ui(()->video(portrait).getCurrentPosition())>begin,"Vertical fullscreen continues playing normally");
            click(p,"touchPane"); click(p,"rotate"); settle(p,Configuration.ORIENTATION_LANDSCAPE); check(ui(()->(Boolean)field(portrait,"fullscreen")),"Manual landscape override remains separate from fullscreen state");
            click(p,"rotate"); settle(p,Configuration.ORIENTATION_PORTRAIT); ui(()->{ invoke(portrait,"setSpeed",float.class,1.25f); invoke(portrait,"setLooping",boolean.class,true); return null; });
            if (ui(()->video(portrait).isPlaying())) click(p,"play");
            Bundle saved=new Bundle(); runOnMainSync(()->callActivityOnSaveInstanceState(portrait,saved)); check(saved.getBoolean("fullscreen")&&saved.getFloat("speed")==1.25f&&saved.getBoolean("looping"),"Fullscreen and playback settings included in recreation state");
            runOnMainSync(()->callActivityOnPause(portrait)); check(!ui(()->video(portrait).isPlaying()),"Background player pauses"); runOnMainSync(()->callActivityOnResume(portrait)); check(!ui(()->video(portrait).isPlaying()),"A deliberately paused video stays paused after returning");
            check(RecordStore.read(context).length()==rows.length(),"Player controls do not change download history"); close(p);
            report.putString("result","PASS: actual vertical/horizontal videos, immersive bars and all buttons hidden, correct auto direction, independent rotation, position preservation, overlay/timer/back, speed/pause, seeks/gestures, window brightness, mute and real loop"); report.putInt("checks",checks); report.putString("portrait_source_id",tall.optString("noteId")); report.putString("scope","Dedicated Android 15 emulator; existing real downloaded Bili and supplied portrait social video; no new downloads or physical phone access"); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); report.putInt("checks",checks); finish(Activity.RESULT_CANCELED,report); }
    }
}
