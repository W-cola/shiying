package cn.shiying.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.PlaybackParams;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;
import cn.shiying.mobile.core.VideoInfo;
import org.json.JSONObject;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Immersive playback and orientation are independent; the video surface stays attached. */
public final class PlayerActivity extends Activity {
    private final Handler handler=new Handler();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private FrameLayout root,frame;
    private LinearLayout header,controls;
    private View touchPane;
    private VideoView videoView;
    private MediaPlayer media;
    private TextView message,play,time,retry,full,rotate,speedButton,loopButton,hud;
    private SeekBar seek;
    private AlertDialog adjustments;
    private PlayerSource source;
    private Future<?> preparation;
    private VideoInfo info;
    private Uri local;
    private int format,position,generation,videoWidth,videoHeight,leftInset,topInset,rightInset,bottomInset;
    private int normalOrientation=Configuration.ORIENTATION_PORTRAIT,manualOrientation=-1;
    private float speed=1f,volume=1f,beforeMute=1f,brightness=-1f;
    private boolean ready,active,wantPlay=true,dragging,destroyed,fallback,completed,fullscreen,controlsShown=true,looping,dialogOpen;
    private int gestureMode,gestureStartPosition,gestureTarget;
    private float gestureVolume,gestureBrightness;
    private final Runnable hideChrome=()->{ if (fullscreen&&ready&&videoView.isPlaying()&&!dragging&&!dialogOpen&&gestureMode==0) setControlsShown(false); };
    private final Runnable hideHud=()->hud.setVisibility(View.GONE);

    static void open(Context context,VideoInfo info,int index) throws Exception {
        context.startActivity(new Intent(context,PlayerActivity.class).putExtra("video",info.toJson().toString()).putExtra("format",index).putExtra("title",info.title));
    }
    static void open(Context context,Uri uri,String title) {
        context.startActivity(new Intent(context,PlayerActivity.class).putExtra("local",uri.toString()).putExtra("title",title));
    }
    private int dp(float n) { return Ui.dp(this,n); }
    private TextView label(String text,int size) { return Ui.text(this,text,size,0xffedf3e8,true); }
    private TextView button(String text) {
        TextView item=label(text,13); item.setGravity(Gravity.CENTER); item.setSingleLine(true); item.setPadding(dp(8),dp(12),dp(8),dp(12));
        Ui.ripple(item,0xff234433,16); item.setMinHeight(dp(48));item.setMinWidth(dp(48));item.setFocusable(true); item.setClickable(true); return item;
    }
    private void rowButton(LinearLayout row,TextView item,boolean first) {
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(48),1); if (!first) p.leftMargin=dp(8); row.addView(item,p);
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); setVolumeControlStream(AudioManager.STREAM_MUSIC);
        if (saved!=null) {
            position=saved.getInt("position"); wantPlay=saved.getBoolean("playing",true); fallback=saved.getBoolean("fallback");
            fullscreen=saved.getBoolean("fullscreen"); controlsShown=saved.getBoolean("controls",!fullscreen);
            normalOrientation=saved.getInt("normalOrientation",Configuration.ORIENTATION_PORTRAIT); manualOrientation=saved.getInt("manualOrientation",-1);
            speed=saved.getFloat("speed",1f); volume=saved.getFloat("volume",1f); beforeMute=saved.getFloat("beforeMute",1f); brightness=saved.getFloat("brightness",-1f); looping=saved.getBoolean("looping");
        }
        getWindow().setStatusBarColor(0xff0d1a14); getWindow().setNavigationBarColor(0xff0d1a14);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        if (Build.VERSION.SDK_INT>=30) { getWindow().setDecorFitsSystemWindows(false); WindowInsetsController bars=getWindow().getInsetsController(); if (bars!=null) bars.setSystemBarsAppearance(0,WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS); }
        root=new FrameLayout(this); root.setBackgroundColor(Color.BLACK); setContentView(root);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            if (Build.VERSION.SDK_INT>=30) {
                android.graphics.Insets safe=insets.getInsetsIgnoringVisibility(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                leftInset=safe.left; topInset=safe.top; rightInset=safe.right; bottomInset=safe.bottom;
            } else { leftInset=insets.getSystemWindowInsetLeft(); topInset=insets.getSystemWindowInsetTop(); rightInset=insets.getSystemWindowInsetRight(); bottomInset=insets.getSystemWindowInsetBottom(); }
            updateLayout(); return insets;
        });
        frame=new FrameLayout(this); frame.setBackgroundColor(Color.BLACK); root.addView(frame,new FrameLayout.LayoutParams(-1,-1));
        videoView=new VideoView(this); frame.addView(videoView,new FrameLayout.LayoutParams(-1,-1,Gravity.CENTER));
        videoView.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build());
        touchPane=new View(this); touchPane.setContentDescription("点按视频；全屏中轻触显示控制，双击播放或暂停"); frame.addView(touchPane,new FrameLayout.LayoutParams(-1,-1));
        message=label("正在准备播放…",13); message.setGravity(Gravity.CENTER); message.setPadding(dp(20),dp(12),dp(20),dp(12)); message.setBackground(Ui.shape(0xd90d1a14,12,0,this));
        FrameLayout.LayoutParams mp=new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER); mp.leftMargin=dp(24); mp.rightMargin=dp(24); frame.addView(message,mp);
        hud=label("",16); hud.setGravity(Gravity.CENTER); hud.setPadding(dp(24),dp(14),dp(24),dp(14)); hud.setBackground(Ui.shape(0xdf0d1a14,14,0,this)); hud.setVisibility(View.GONE); frame.addView(hud,new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER));
        header=new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL); header.setBackgroundColor(0xe60d1a14); root.addView(header,new FrameLayout.LayoutParams(-1,-2,Gravity.TOP));
        TextView back=button("‹ 返回"); back.setOnClickListener(v->onBackPressed()); header.addView(back);
        TextView title=label(getIntent().getStringExtra("title"),15); title.setMaxLines(2); title.setEllipsize(android.text.TextUtils.TruncateAt.END); title.setPadding(dp(12),0,dp(8),0); header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        retry=button("重试"); retry.setVisibility(View.GONE); retry.setOnClickListener(v->prepare()); header.addView(retry);
        controls=new LinearLayout(this); controls.setOrientation(LinearLayout.VERTICAL); controls.setBackgroundColor(0xe60d1a14); root.addView(controls,new FrameLayout.LayoutParams(-1,-2,Gravity.BOTTOM));
        LinearLayout progress=new LinearLayout(this); progress.setGravity(Gravity.CENTER_VERTICAL); controls.addView(progress,new LinearLayout.LayoutParams(-1,dp(40)));
        seek=new SeekBar(this); seek.setMax(1000); seek.setEnabled(false); seek.setContentDescription("播放进度"); seek.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.LIME)); seek.setThumbTintList(android.content.res.ColorStateList.valueOf(Ui.LIME)); progress.addView(seek,new LinearLayout.LayoutParams(0,-2,1));
        time=label("00:00 / 00:00",11); progress.addView(time);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onStartTrackingTouch(SeekBar bar) { dragging=true; handler.removeCallbacks(hideChrome); }
            public void onProgressChanged(SeekBar bar,int value,boolean user) { if (user&&ready) time.setText(clock((int)((long)videoView.getDuration()*value/1000))+" / "+clock(videoView.getDuration())); }
            public void onStopTrackingTouch(SeekBar bar) { if (ready) seekTo((int)((long)videoView.getDuration()*bar.getProgress()/1000)); dragging=false; scheduleHide(); }
        });
        LinearLayout actions=new LinearLayout(this); actions.setGravity(Gravity.CENTER_VERTICAL); controls.addView(actions);
        play=button("播放"); play.setEnabled(false); play.setOnClickListener(v->toggle()); rowButton(actions,play,true);
        TextView rewind=button("−15 秒"); rewind.setOnClickListener(v->{ jump(-15000); scheduleHide(); }); rowButton(actions,rewind,false);
        TextView forward=button("+15 秒"); forward.setOnClickListener(v->{ jump(15000); scheduleHide(); }); rowButton(actions,forward,false);
        full=button("全屏"); full.setOnClickListener(v->setFullscreen(!fullscreen)); rowButton(actions,full,false);
        LinearLayout extras=new LinearLayout(this); extras.setGravity(Gravity.CENTER_VERTICAL); LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(-1,-2); ep.topMargin=dp(8); controls.addView(extras,ep);
        speedButton=button("1.0×"); speedButton.setContentDescription("播放倍速"); speedButton.setOnClickListener(v->chooseSpeed()); rowButton(extras,speedButton,true);
        loopButton=button("循环关"); loopButton.setOnClickListener(v->setLooping(!looping)); rowButton(extras,loopButton,false);
        rotate=button("横屏"); rotate.setOnClickListener(v->rotateScreen()); rowButton(extras,rotate,false);
        TextView more=button("音量亮度"); more.setOnClickListener(v->showAdjustments()); rowButton(extras,more,false);
        TextView hint=label("全屏轻触显示控制 · 左右滑动进度 · 左侧亮度 / 右侧音量",10); hint.setTextColor(0xff93a78e); hint.setGravity(Gravity.CENTER); hint.setPadding(0,dp(8),0,0); controls.addView(hint);
        header.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->updateVideoBounds()); controls.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->updateVideoBounds());
        initGestures();
        videoView.setOnPreparedListener(player->{
            if (destroyed) return; media=player; ready=true; completed=false; showMessage(""); retry.setVisibility(View.GONE); seek.setEnabled(true); play.setEnabled(true);
            videoWidth=player.getVideoWidth(); videoHeight=player.getVideoHeight(); player.setLooping(looping); player.setVolume(volume,volume);
            applySpeed(speed); if (position>0) videoView.seekTo(position); if (active&&wantPlay) videoView.start();
            player.setOnVideoSizeChangedListener((p,w,h)->{ videoWidth=w; videoHeight=h; if (fullscreen&&manualOrientation==-1) applyOrientation(); });
            if (fullscreen) applyOrientation(); updateControls(); scheduleHide();
        });
        videoView.setOnInfoListener((player,what,extra)->{
            if (what==MediaPlayer.MEDIA_INFO_BUFFERING_START) showMessage("正在缓冲…");
            else if (what==MediaPlayer.MEDIA_INFO_BUFFERING_END||what==MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) showMessage(""); return false;
        });
        videoView.setOnCompletionListener(player->{ completed=true; wantPlay=false; position=0; setControlsShown(true); updateControls(); });
        videoView.setOnErrorListener((player,what,extra)->{
            if (ready) position=videoView.getCurrentPosition(); ready=false; media=null; videoView.stopPlayback();
            if (info!=null&&!fallback&&"direct".equals(info.formats.get(format).mode)) { fallback=true; prepare(); }
            else failure("播放失败，请重试或返回重新解析。手机系统需要支持此视频编码。"); return true;
        });
        try {
            String json=getIntent().getStringExtra("video"),uri=getIntent().getStringExtra("local");
            if (json!=null) { info=VideoInfo.fromJson(new JSONObject(json)); format=getIntent().getIntExtra("format",0); if (info.isImages()||format<0||format>=info.formats.size()) throw new Exception(); videoWidth=info.formats.get(format).width; videoHeight=info.formats.get(format).height; }
            else { local=Uri.parse(uri==null?"":uri); if (!"content".equals(local.getScheme())) throw new Exception(); }
            applyBrightness(); applyOrientation(); setControlsShown(controlsShown); applyBars(); prepare();
        } catch (Exception e) { failure("没有有效的视频，请返回重新选择。"); retry.setVisibility(View.GONE); }
    }
    private void showMessage(String text) { message.setText(text); message.setVisibility(text.isEmpty()?View.GONE:View.VISIBLE); }
    private void prepare() {
        if (destroyed) return; int token=++generation;
        if (preparation!=null) preparation.cancel(true); if (source!=null) source.close(); videoView.stopPlayback(); media=null; ready=false; completed=false;
        play.setEnabled(false); seek.setEnabled(false); retry.setVisibility(View.GONE); showMessage(fallback?"正在切换缓存播放…":"正在准备播放…");
        if (local!=null) { videoView.setVideoURI(local); return; }
        final PlayerSource session=new PlayerSource(this,text->handler.post(()->{ if (!destroyed&&generation==token) showMessage(text); })); source=session;
        preparation=worker.submit(()->{
            try { PlayerSource.Ready result=session.prepare(info,format,fallback); handler.post(()->{ if (destroyed||generation!=token) { session.close(); return; } showMessage("正在加载视频…"); videoView.setVideoURI(result.uri,result.headers); }); }
            catch (Exception e) { handler.post(()->{ if (!destroyed&&generation==token) failure(e.getMessage()==null?"无法播放，请返回重新解析。":e.getMessage()); }); }
        });
    }
    private void failure(String text) { ready=false; play.setEnabled(false); seek.setEnabled(false); showMessage(text); retry.setVisibility(View.VISIBLE); setControlsShown(true); getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); }
    private void toggle() {
        if (!ready) return; wantPlay=!videoView.isPlaying(); if (wantPlay) { if (completed) { videoView.seekTo(0); completed=false; } videoView.start(); } else { videoView.pause(); setControlsShown(true); }
        updateControls(); scheduleHide();
    }
    private void seekTo(int target) { if (ready) { completed=false; position=Math.max(0,Math.min(videoView.getDuration(),target)); videoView.seekTo(position); updateControls(); } }
    private void jump(int delta) { if (ready) { seekTo(videoView.getCurrentPosition()+delta); showHud((delta>0?"+":"−")+(Math.abs(delta)/1000)+" 秒"); handler.postDelayed(hideHud,700); } }
    private static String clock(int milliseconds) { int seconds=Math.max(0,milliseconds)/1000; return seconds>=3600?String.format(Locale.ROOT,"%d:%02d:%02d",seconds/3600,seconds/60%60,seconds%60):String.format(Locale.ROOT,"%02d:%02d",seconds/60,seconds%60); }
    private void updateControls() {
        full.setText(fullscreen?"退出全屏":"全屏"); rotate.setText(getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE?"竖屏":"横屏");
        loopButton.setText(looping?"循环开":"循环关"); speedButton.setText(String.format(Locale.ROOT,"%s×",speed==(int)speed?String.format(Locale.ROOT,"%.1f",speed):String.valueOf(speed)));
        if (!ready) return; boolean playing=videoView.isPlaying(); play.setText(playing?"暂停":completed?"重播":"播放");
        if (playing) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (!dragging&&gestureMode!=1) { int current=completed?videoView.getDuration():videoView.getCurrentPosition(),duration=videoView.getDuration(); seek.setProgress(duration>0?(int)((long)current*1000/duration):0); time.setText(clock(current)+" / "+clock(duration)); }
    }
    private void setFullscreen(boolean value) {
        if (fullscreen==value) return;
        if (ready) position=videoView.getCurrentPosition();
        if (value) { normalOrientation=getResources().getConfiguration().orientation; manualOrientation=-1; }
        fullscreen=value; setControlsShown(!value); applyOrientation(); applyBars(); updateLayout(); updateControls();
    }
    private void setControlsShown(boolean value) {
        controlsShown=value||!fullscreen; header.setVisibility(controlsShown?View.VISIBLE:View.GONE); controls.setVisibility(controlsShown?View.VISIBLE:View.GONE);
        updateLayout(); scheduleHide();
    }
    private void scheduleHide() { handler.removeCallbacks(hideChrome); if (fullscreen&&controlsShown&&ready&&videoView.isPlaying()&&!dragging&&!dialogOpen) handler.postDelayed(hideChrome,3000); }
    private void applyOrientation() {
        int orientation=normalOrientation;
        if (fullscreen) { if (manualOrientation!=-1) orientation=manualOrientation; else if (videoWidth>videoHeight*1.05) orientation=Configuration.ORIENTATION_LANDSCAPE; else if (videoHeight>videoWidth*1.05) orientation=Configuration.ORIENTATION_PORTRAIT; else orientation=getResources().getConfiguration().orientation; }
        int desired=orientation==Configuration.ORIENTATION_LANDSCAPE?ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE:ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT;
        if (getRequestedOrientation()!=desired) setRequestedOrientation(desired);
    }
    private void rotateScreen() {
        if (ready) position=videoView.getCurrentPosition();
        int value=getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE?Configuration.ORIENTATION_PORTRAIT:Configuration.ORIENTATION_LANDSCAPE;
        if (fullscreen) manualOrientation=value; else normalOrientation=value;
        applyOrientation(); scheduleHide();
    }
    private void applyBars() {
        if (Build.VERSION.SDK_INT>=28) { WindowManager.LayoutParams p=getWindow().getAttributes(); p.layoutInDisplayCutoutMode=fullscreen?WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES:WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_DEFAULT; getWindow().setAttributes(p); }
        if (Build.VERSION.SDK_INT>=30) {
            WindowInsetsController controller=getWindow().getInsetsController(); if (controller!=null) { controller.setSystemBarsAppearance(0,WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS); controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE); if (fullscreen) controller.hide(WindowInsets.Type.systemBars()); else controller.show(WindowInsets.Type.systemBars()); }
        } else getWindow().getDecorView().setSystemUiVisibility(fullscreen?View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY:View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        root.requestApplyInsets();
    }
    private void updateLayout() {
        if (header==null||controls==null) return;
        root.setPadding(fullscreen?0:leftInset,fullscreen?0:topInset,fullscreen?0:rightInset,fullscreen?0:bottomInset);
        header.setPadding(dp(12)+(fullscreen?leftInset:0),dp(8)+(fullscreen?topInset:0),dp(12)+(fullscreen?rightInset:0),dp(8));
        controls.setPadding(dp(12)+(fullscreen?leftInset:0),dp(8),dp(12)+(fullscreen?rightInset:0),dp(10)+(fullscreen?bottomInset:0)); updateVideoBounds();
    }
    private void updateVideoBounds() {
        if (frame==null||header==null||controls==null) return; FrameLayout.LayoutParams p=(FrameLayout.LayoutParams)frame.getLayoutParams();
        int top=fullscreen?0:header.getHeight(),bottom=fullscreen?0:controls.getHeight();
        if (p.topMargin!=top||p.bottomMargin!=bottom) { p.topMargin=top; p.bottomMargin=bottom; frame.setLayoutParams(p); }
    }
    private void dialogClosed() { dialogOpen=false; applyBars(); scheduleHide(); }
    private void chooseSpeed() {
        dialogOpen=true; handler.removeCallbacks(hideChrome); float[] values={.5f,.75f,1f,1.25f,1.5f,2f}; String[] labels={"0.5×","0.75×","1.0×","1.25×","1.5×","2.0×"}; int selected=2; for (int i=0;i<values.length;i++) if (values[i]==speed) selected=i;
        Ui.Sheet dialog=Ui.sheet(this,"播放倍速","调整速度，声音保持原音调。","audio"); for(int i=0;i<values.length;i++){final float value=values[i];dialog.action("check",labels[i],i==selected?"当前速度":"",()->setSpeed(value));} dialog.setOnDismissListener(d->dialogClosed()); dialog.show();
    }
    private void applySpeed(float value) {
        if (!ready||media==null) return; boolean paused=!active||!wantPlay||completed;
        try { media.setPlaybackParams(new PlaybackParams().allowDefaults().setSpeed(value).setPitch(1f)); if (paused) media.pause(); }
        catch (Exception e) { speed=1f; Toast.makeText(this,"这个视频暂不支持所选倍速。",Toast.LENGTH_SHORT).show(); }
    }
    private void setSpeed(float value) { speed=value; applySpeed(value); updateControls(); scheduleHide(); }
    private void setLooping(boolean value) { looping=value; if (ready&&media!=null) media.setLooping(value); updateControls(); scheduleHide(); }
    private void setVolume(float value) { volume=Math.max(0,Math.min(1,value)); if (volume>0) beforeMute=volume; if (ready&&media!=null) media.setVolume(volume,volume); }
    private float effectiveBrightness() { return brightness>=0?brightness:Settings.System.getInt(getContentResolver(),Settings.System.SCREEN_BRIGHTNESS,128)/255f; }
    private void applyBrightness() {
        WindowManager.LayoutParams p=getWindow().getAttributes(); p.screenBrightness=brightness; getWindow().setAttributes(p);
        if (adjustments!=null&&adjustments.getWindow()!=null) { WindowManager.LayoutParams d=adjustments.getWindow().getAttributes(); d.screenBrightness=brightness; adjustments.getWindow().setAttributes(d); }
    }
    private void setBrightness(float value) { brightness=Math.max(.05f,Math.min(1,value)); applyBrightness(); }
    private void showAdjustments() {
        dialogOpen=true; handler.removeCallbacks(hideChrome); LinearLayout content=new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(20),dp(8),dp(20),dp(8));
        TextView audio=Ui.text(this,"播放器音量",14,Ui.INK,true); content.addView(audio); SeekBar audioBar=new SeekBar(this); audioBar.setMax(100); audioBar.setProgress(Math.round(volume*100)); content.addView(audioBar);
        TextView light=Ui.text(this,"亮度（仅当前播放器）",14,Ui.INK,true); light.setPadding(0,dp(16),0,0); content.addView(light); SeekBar lightBar=new SeekBar(this); lightBar.setMax(100); lightBar.setProgress(Math.round(effectiveBrightness()*100)); content.addView(lightBar);
        final TextView mute=Ui.text(this,volume==0?"恢复声音":"静音",14,Ui.GREEN,true);
        audioBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() { public void onStartTrackingTouch(SeekBar bar){} public void onStopTrackingTouch(SeekBar bar){} public void onProgressChanged(SeekBar bar,int value,boolean user){ if (user) setVolume(value/100f); audio.setText("播放器音量  "+value+"%"); mute.setText(volume==0?"恢复声音":"静音"); } });
        lightBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() { public void onStartTrackingTouch(SeekBar bar){} public void onStopTrackingTouch(SeekBar bar){} public void onProgressChanged(SeekBar bar,int value,boolean user){ if (user) setBrightness(value/100f); light.setText("亮度  "+Math.max(5,value)+"%（仅当前播放器）"); } });
        LinearLayout row=new LinearLayout(this); content.addView(row); mute.setPadding(dp(12),dp(16),dp(12),dp(16)); mute.setOnClickListener(v->{ setVolume(volume==0?beforeMute:0); audioBar.setProgress(Math.round(volume*100)); mute.setText(volume==0?"恢复声音":"静音"); }); row.addView(mute);
        TextView system=Ui.text(this,"跟随系统亮度",14,Ui.GREEN,true); system.setPadding(dp(12),dp(16),dp(12),dp(16)); system.setOnClickListener(v->{ brightness=-1; applyBrightness(); lightBar.setProgress(Math.round(effectiveBrightness()*100)); }); row.addView(system);
        adjustments=new AlertDialog.Builder(this).setTitle("声音与亮度").setView(content).setPositiveButton("完成",null).create(); adjustments.setOnDismissListener(d->{ adjustments=null; dialogClosed(); }); adjustments.show(); Ui.styleDialog(adjustments); applyBrightness();
    }
    private void showHud(String text) { handler.removeCallbacks(hideHud); hud.setText(text); hud.setVisibility(View.VISIBLE); }
    private void initGestures() {
        GestureDetector detector=new GestureDetector(this,new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onDown(MotionEvent event) { gestureMode=0; gestureStartPosition=ready?videoView.getCurrentPosition():0; gestureTarget=gestureStartPosition; gestureVolume=volume; gestureBrightness=effectiveBrightness(); handler.removeCallbacks(hideChrome); return true; }
            @Override public boolean onSingleTapConfirmed(MotionEvent event) { touchPane.performClick(); return true; }
            @Override public boolean onDoubleTap(MotionEvent event) { toggle(); return true; }
            @Override public boolean onScroll(MotionEvent start,MotionEvent end,float dxIgnored,float dyIgnored) {
                if (start==null) return false; float dx=end.getX()-start.getX(),dy=start.getY()-end.getY();
                if (gestureMode==0&&Math.max(Math.abs(dx),Math.abs(dy))>dp(20)) gestureMode=Math.abs(dx)>Math.abs(dy)?1:(start.getX()<touchPane.getWidth()/2f?2:3);
                if (gestureMode==1&&ready) { gestureTarget=Math.max(0,Math.min(videoView.getDuration(),gestureStartPosition+Math.round(dx/Math.max(1,touchPane.getWidth())*Math.min(videoView.getDuration(),180000)))); showHud(clock(gestureTarget)+" / "+clock(videoView.getDuration())); }
                else if (gestureMode==2) { setBrightness(gestureBrightness+dy/Math.max(1,touchPane.getHeight())*1.5f); showHud("亮度  "+Math.round(brightness*100)+"%"); }
                else if (gestureMode==3) { setVolume(gestureVolume+dy/Math.max(1,touchPane.getHeight())*1.5f); showHud("音量  "+Math.round(volume*100)+"%"); }
                return true;
            }
        });
        touchPane.setOnClickListener(v->{ if (fullscreen) setControlsShown(!controlsShown); else toggle(); });
        touchPane.setOnTouchListener((v,event)->{ detector.onTouchEvent(event); if (event.getAction()==MotionEvent.ACTION_UP||event.getAction()==MotionEvent.ACTION_CANCEL) { if (gestureMode==1&&event.getAction()==MotionEvent.ACTION_UP) seekTo(gestureTarget); if (gestureMode!=0) handler.postDelayed(hideHud,700); gestureMode=0; scheduleHide(); } return true; });
    }
    private final Runnable tick=new Runnable() { public void run() { if (active&&!destroyed) { updateControls(); handler.postDelayed(this,250); } } };
    @Override protected void onResume() { super.onResume(); active=true; if (ready&&wantPlay) videoView.start(); applyBars(); handler.post(tick); scheduleHide(); }
    @Override protected void onPause() { active=false; handler.removeCallbacks(tick); handler.removeCallbacks(hideChrome); if (ready) { position=videoView.getCurrentPosition(); videoView.pause(); } getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); super.onPause(); }
    @Override public void onWindowFocusChanged(boolean focus) { super.onWindowFocusChanged(focus); if (focus&&root!=null) { applyBars(); scheduleHide(); } }
    @Override public void onConfigurationChanged(Configuration configuration) { super.onConfigurationChanged(configuration); applyBars(); updateLayout(); updateControls(); }
    @Override public void onBackPressed() { if (fullscreen) setFullscreen(false); else super.onBackPressed(); }
    @Override protected void onSaveInstanceState(Bundle saved) {
        saved.putInt("position",ready?videoView.getCurrentPosition():position); saved.putBoolean("playing",wantPlay); saved.putBoolean("fallback",fallback); saved.putBoolean("fullscreen",fullscreen); saved.putBoolean("controls",controlsShown); saved.putInt("normalOrientation",normalOrientation); saved.putInt("manualOrientation",manualOrientation);
        saved.putFloat("speed",speed); saved.putFloat("volume",volume); saved.putFloat("beforeMute",beforeMute); saved.putFloat("brightness",brightness); saved.putBoolean("looping",looping); super.onSaveInstanceState(saved);
    }
    @Override protected void onDestroy() { destroyed=true; generation++; handler.removeCallbacksAndMessages(null); videoView.stopPlayback(); media=null; if (preparation!=null) preparation.cancel(true); if (source!=null) source.close(); worker.shutdownNow(); super.onDestroy(); }
}
