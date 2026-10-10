package cn.shiying.mobile;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.ClipData;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.media.MediaPlayer;
import android.media.AudioAttributes;
import android.media.PlaybackParams;
import android.media.AudioManager;
import android.media.AudioFocusRequest;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.content.BroadcastReceiver;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import java.util.Locale;

/** App-owned saved audio playback; no external player or microphone permission. */
public final class AudioActivity extends Activity {
    private MediaPlayer media; private Uri uri; private final Handler handler=new Handler();
    private TextView play,time,rate,loop; private SeekBar seek; private Wave art;
    private boolean ready,active,wantPlay=true,dragging,looping; private int position; private float speed=1;
    private AudioManager audioManager; private AudioFocusRequest focus; private MediaSession session; private boolean receiverRegistered;
    private final BroadcastReceiver noisy=new BroadcastReceiver(){public void onReceive(Context c,Intent intent){pauseAudio();}};
    static void open(Context context,Uri uri,String title) { context.startActivity(new Intent(context,AudioActivity.class).putExtra("uri",uri.toString()).putExtra("title",title)); }
    private TextView button(String title) { TextView v=Ui.text(this,title,15,Ui.GREEN,true); v.setGravity(Gravity.CENTER); v.setPadding(Ui.dp(this,12),Ui.dp(this,14),Ui.dp(this,12),Ui.dp(this,14)); v.setMinHeight(Ui.dp(this,52)); Ui.ripple(v,Ui.SOFT,18); return v; }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        audioManager=(AudioManager)getSystemService(AUDIO_SERVICE);
        focus=new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()).setOnAudioFocusChangeListener(change->{ if(!ready)return;if(change==AudioManager.AUDIOFOCUS_LOSS){pauseAudio();}else if(change==AudioManager.AUDIOFOCUS_LOSS_TRANSIENT){media.pause();update();}else if(change==AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK){media.setVolume(.2f,.2f);}else if(change==AudioManager.AUDIOFOCUS_GAIN){media.setVolume(1,1);if(active&&wantPlay)media.start();update();} }).build();
        session=new MediaSession(this,"拾影原声");session.setCallback(new MediaSession.Callback(){@Override public void onPlay(){wantPlay=true;startAudio();}@Override public void onPause(){pauseAudio();}@Override public void onStop(){pauseAudio();}@Override public void onSeekTo(long p){if(ready)media.seekTo((int)Math.max(0,Math.min(media.getDuration(),p)));}});
        if (saved!=null) { position=saved.getInt("position"); wantPlay=saved.getBoolean("playing",true); speed=saved.getFloat("speed",1); looping=saved.getBoolean("looping"); }
        getWindow().setStatusBarColor(Ui.BG); getWindow().setNavigationBarColor(Ui.BG);
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(Ui.dp(this,24),Ui.dp(this,18),Ui.dp(this,24),Ui.dp(this,24)); root.setBackgroundColor(Ui.BG);
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setVerticalScrollBarEnabled(false); scroll.addView(root); setContentView(scroll);
        LinearLayout header=new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL); TextView back=button("返回"); back.setOnClickListener(v->finish()); header.addView(back);
        TextView label=Ui.text(this,"拾影 · 原声音频",14,Ui.MUTED,true); label.setGravity(Gravity.CENTER); header.addView(label,new LinearLayout.LayoutParams(0,-2,1)); TextView share=button("分享"); share.setOnClickListener(v->share()); header.addView(share); root.addView(header);
        TextView tag=Ui.text(this,"A MOMENT TO LISTEN",11,Ui.MUTED,true); tag.setLetterSpacing(.12f); tag.setGravity(Gravity.CENTER); tag.setPadding(0,Ui.dp(this,32),0,Ui.dp(this,18)); root.addView(tag);
        art=new Wave(this); int height=Math.min(300,Math.max(180,getResources().getConfiguration().screenWidthDp-64)); root.addView(art,new LinearLayout.LayoutParams(-1,Ui.dp(this,height)));
        TextView title=Ui.text(this,getIntent().getStringExtra("title"),23,Ui.INK,true); title.setGravity(Gravity.CENTER); title.setMaxLines(3); title.setPadding(0,Ui.dp(this,24),0,Ui.dp(this,8)); root.addView(title);
        TextView sub=Ui.text(this,"独立音频 · M4A  /  保存在音乐 · 拾影",12,Ui.MUTED,false); sub.setGravity(Gravity.CENTER); root.addView(sub);
        seek=new SeekBar(this); seek.setMax(1000); seek.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.GREEN)); seek.setThumbTintList(android.content.res.ColorStateList.valueOf(Ui.GREEN)); seek.setContentDescription("音频播放进度"); LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(-1,Ui.dp(this,48)); sp.topMargin=Ui.dp(this,26); root.addView(seek,sp);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() { public void onStartTrackingTouch(SeekBar s){ dragging=true; } public void onProgressChanged(SeekBar s,int p,boolean user){} public void onStopTrackingTouch(SeekBar s){ if (ready) media.seekTo((int)((long)media.getDuration()*s.getProgress()/1000)); dragging=false; } });
        time=Ui.text(this,"正在读取音频…",12,Ui.MUTED,false); time.setGravity(Gravity.CENTER); root.addView(time);
        LinearLayout primary=new LinearLayout(this); LinearLayout.LayoutParams ap=new LinearLayout.LayoutParams(-1,-2); ap.topMargin=Ui.dp(this,22); root.addView(primary,ap);
        TextView rewind=button("−15 秒"),forward=button("+15 秒"); play=button("播放"); play.setTextColor(Ui.WHITE); Ui.ripple(play,Ui.GREEN,22); play.setEnabled(false);
        add(primary,rewind); add(primary,play); add(primary,forward); rewind.setOnClickListener(v->jump(-15000)); forward.setOnClickListener(v->jump(15000)); play.setOnClickListener(v->toggle());
        LinearLayout secondary=new LinearLayout(this); LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(-1,-2); ep.topMargin=Ui.dp(this,14); root.addView(secondary,ep); rate=button(speed+"×"); loop=button(looping?"循环开":"循环关"); add(secondary,rate); add(secondary,loop);
        rate.setOnClickListener(v->{ Ui.Sheet sheet=Ui.sheet(this,"播放倍速","选择适合你的听感","audio"); for (float value:new float[]{.5f,.75f,1,1.25f,1.5f,2}) sheet.action("check",value+"×",value==speed?"当前速度":"",()->setSpeed(value)); sheet.show(); }); loop.setOnClickListener(v->{ looping=!looping; if (ready) media.setLooping(looping); loop.setText(looping?"循环开":"循环关"); });
        TextView hint=Ui.text(this,"分享音频，可直接用于剪辑或其他播放器。",12,Ui.MUTED,false); hint.setGravity(Gravity.CENTER); hint.setPadding(0,Ui.dp(this,24),0,0); root.addView(hint);
        try {
            uri=Uri.parse(getIntent().getStringExtra("uri")); if (!"content".equals(uri.getScheme())) throw new Exception();
            media=new MediaPlayer(); media.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()); media.setDataSource(this,uri);
            media.setOnPreparedListener(m->{ ready=true; play.setEnabled(true); m.setLooping(looping); setSpeed(speed); if (position>0) m.seekTo(position); if (active&&wantPlay) startAudio(); update(); });
            media.setOnCompletionListener(m->{ wantPlay=false; position=0; audioManager.abandonAudioFocusRequest(focus);update(); }); media.setOnErrorListener((m,w,e)->{ ready=false; play.setEnabled(false); time.setText("无法播放，请返回重新提取。"); return true; }); media.prepareAsync();
        } catch (Exception error) { Ui.notice(this,"音频暂时无法读取","文件可能已被移除，请返回「我的片段」重新提取。"); }
        Ui.appear(root);
    }
    private void add(LinearLayout row,View item) { LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,Ui.dp(this,56),1); if (row.getChildCount()>0) p.leftMargin=Ui.dp(this,10); row.addView(item,p); }
    private void startAudio(){if(!ready||!active)return;if(audioManager.requestAudioFocus(focus)==AudioManager.AUDIOFOCUS_REQUEST_GRANTED){media.start();update();}else{wantPlay=false;media.pause();update();}}
    private void pauseAudio(){wantPlay=false;if(ready){media.pause();update();}audioManager.abandonAudioFocusRequest(focus);}
    private void toggle() { if (!ready) return; wantPlay=!media.isPlaying(); if (wantPlay) { if (media.getCurrentPosition()>=media.getDuration()-80) media.seekTo(0); startAudio(); } else pauseAudio(); update(); }
    private void jump(int amount) { if (ready) media.seekTo(Math.max(0,Math.min(media.getDuration(),media.getCurrentPosition()+amount))); }
    private void setSpeed(float value) { speed=value; if (ready) try { media.setPlaybackParams(new PlaybackParams().allowDefaults().setSpeed(value).setPitch(1)); if (!active||!wantPlay) media.pause(); } catch (Exception e) { speed=1; } rate.setText(speed+"×"); }
    private void share() { if (uri==null) return; Intent share=new Intent(Intent.ACTION_SEND).setType("audio/mp4").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); share.setClipData(ClipData.newRawUri("audio",uri)); startActivity(Intent.createChooser(share,"分享原声音频")); }
    private String clock(int ms) { return String.format(Locale.ROOT,"%02d:%02d",ms/60000,ms/1000%60); }
    private void update() { if (!ready) return; boolean playing=media.isPlaying(); play.setText(playing?"暂停":"播放"); if (!dragging) seek.setProgress((int)((long)media.getCurrentPosition()*1000/Math.max(1,media.getDuration()))); time.setText(clock(media.getCurrentPosition())+"  /  "+clock(media.getDuration())); art.playing=playing; art.invalidate();session.setPlaybackState(new PlaybackState.Builder().setActions(PlaybackState.ACTION_PLAY|PlaybackState.ACTION_PAUSE|PlaybackState.ACTION_PLAY_PAUSE|PlaybackState.ACTION_SEEK_TO).setState(playing?PlaybackState.STATE_PLAYING:PlaybackState.STATE_PAUSED,media.getCurrentPosition(),speed).build()); }
    private final Runnable tick=new Runnable() { public void run(){ if (active) { update(); handler.postDelayed(this,200); } } };
    @Override protected void onResume(){ super.onResume(); active=true;session.setActive(true);if(!receiverRegistered){registerReceiver(noisy,new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY));receiverRegistered=true;}if (ready&&wantPlay) startAudio(); handler.post(tick); }
    @Override protected void onPause(){ active=false; handler.removeCallbacks(tick); if (ready) { position=media.getCurrentPosition(); media.pause(); } audioManager.abandonAudioFocusRequest(focus);session.setActive(false);if(receiverRegistered){unregisterReceiver(noisy);receiverRegistered=false;}super.onPause(); }
    @Override protected void onSaveInstanceState(Bundle out){ out.putInt("position",ready?media.getCurrentPosition():position); out.putBoolean("playing",wantPlay); out.putFloat("speed",speed); out.putBoolean("looping",looping); super.onSaveInstanceState(out); }
    @Override protected void onDestroy(){ handler.removeCallbacksAndMessages(null); if (media!=null) media.release();session.release();audioManager.abandonAudioFocusRequest(focus);ready=false;super.onDestroy(); }
    private static final class Wave extends View {
        final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG); boolean playing;
        Wave(Context c){ super(c); setContentDescription("原声音频封面"); }
        @Override protected void onDraw(Canvas c){ c.save(); float size=Math.min(getWidth(),getHeight()); c.translate((getWidth()-size)/2,(getHeight()-size)/2); c.scale(size/240,size/240); p.setColor(Ui.SOFT); c.drawCircle(120,120,118,p); p.setColor(0xffc4d7b2); c.drawCircle(120,120,94,p); p.setColor(Ui.GREEN); c.drawCircle(120,120,79,p); p.setColor(Ui.LIME); double phase=playing&&Ui.motion()?android.os.SystemClock.uptimeMillis()/240.0:0; for(int i=0;i<17;i++){ float h=12+(float)(Math.abs(Math.sin(i*.7+phase))*45); c.drawRoundRect(54+i*8,120-h,58+i*8,120+h,3,3,p); } c.restore(); }
    }
}
