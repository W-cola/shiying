package cn.shiying.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Native swipe gallery for a resolved post or a saved collection; no external viewer. */
public final class ImageActivity extends Activity {
    private final Handler handler=new Handler();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private ImageView image;
    private TextView count,message,previous,next;
    private VideoInfo info;
    private JSONObject album;
    private JSONArray items;
    private List<VideoInfo.Asset> assets;
    private File cache;
    private Future<?> request;
    private volatile HttpURLConnection connection;
    private int index,generation;
    private boolean destroyed;
    private float downX,downY;
    static void open(Context context,VideoInfo info,int selected) throws Exception {
        int start=0; List<VideoInfo.Asset> all=info.selectedAssets(info.formats.get(0));
        if (selected>=0&&selected<info.formats.size()) { List<VideoInfo.Asset> chosen=info.selectedAssets(info.formats.get(selected)); if (chosen.size()==1) for (int i=0;i<all.size();i++) if (all.get(i).index==chosen.get(0).index) start=i; }
        context.startActivity(new Intent(context,ImageActivity.class).putExtra("video",info.toJson().toString()).putExtra("index",start));
    }
    static void open(Context context,JSONObject album) { context.startActivity(new Intent(context,ImageActivity.class).putExtra("album",album.toString())); }
    private int dp(float n) { return Ui.dp(this,n); }
    private TextView button(String text) { TextView v=Ui.text(this,text,14,0xffeef5e8,true); v.setGravity(Gravity.CENTER); v.setMinHeight(dp(48));v.setMinWidth(dp(48));v.setPadding(dp(14),dp(12),dp(14),dp(12)); Ui.ripple(v,0xff234433,16); v.setClickable(true); v.setFocusable(true); return v; }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); getWindow().setStatusBarColor(0xff0d1a14); getWindow().setNavigationBarColor(0xff0d1a14); getWindow().getDecorView().setSystemUiVisibility(0);
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(0xff0d1a14); setContentView(root);
        root.setOnApplyWindowInsetsListener((v,insets)->{ v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom()); return insets; });
        try {
            String json=getIntent().getStringExtra("video");
            if (json!=null) { info=VideoInfo.fromJson(new JSONObject(json)); if (!info.isImages()||info.formats.isEmpty()) throw new Exception(); assets=info.selectedAssets(info.formats.get(0)); }
            else { album=new JSONObject(getIntent().getStringExtra("album")); items=AlbumRecords.images(album); }
            if (total()==0) throw new Exception();
        } catch (Exception e) { Ui.Sheet error=Ui.sheet(this,"暂时无法预览","没有可预览的图片，请返回重新解析。","image").action("arrow","返回","",true,()->finish());error.setOnCancelListener(d->finish());error.show();return; }
        index=Math.max(0,Math.min(total()-1,saved==null?getIntent().getIntExtra("index",0):saved.getInt("index")));
        cache=new File(getCacheDir(),"images_"+UUID.randomUUID());
        LinearLayout header=new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL); header.setPadding(dp(12),dp(8),dp(12),dp(8)); root.addView(header,new LinearLayout.LayoutParams(-1,-2));
        TextView back=button("‹ 返回"); back.setOnClickListener(v->finish()); header.addView(back);
        TextView title=Ui.text(this,info!=null?info.title:album.optString("title"),15,0xffeef5e8,true); title.setMaxLines(2); title.setEllipsize(android.text.TextUtils.TruncateAt.END); title.setPadding(dp(12),0,dp(8),0); header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        TextView more=button("⋯"); more.setContentDescription("图文选项"); more.setOnClickListener(v->options()); header.addView(more);
        FrameLayout frame=new FrameLayout(this); frame.setBackgroundColor(0xff080e0b); root.addView(frame,new LinearLayout.LayoutParams(-1,0,1));
        image=new ImageView(this); image.setScaleType(ImageView.ScaleType.FIT_CENTER); image.setContentDescription("图文图片，左右滑动切换"); frame.addView(image,new FrameLayout.LayoutParams(-1,-1));
        message=Ui.text(this,"",13,0xffb9caba,false); message.setGravity(Gravity.CENTER); message.setPadding(dp(24),dp(24),dp(24),dp(24)); frame.addView(message,new FrameLayout.LayoutParams(-1,-1)); message.setClickable(false);
        frame.setOnTouchListener((v,event)->swipe(event)); image.setOnTouchListener((v,event)->swipe(event)); message.setOnTouchListener((v,event)->swipe(event));
        LinearLayout bar=new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL); bar.setPadding(dp(16),dp(12),dp(16),dp(10)); root.addView(bar,new LinearLayout.LayoutParams(-1,-2));
        previous=button("‹ 上一张"); previous.setOnClickListener(v->move(-1)); bar.addView(previous);
        count=Ui.text(this,"",14,0xffeef5e8,true); count.setGravity(Gravity.CENTER); bar.addView(count,new LinearLayout.LayoutParams(0,-2,1));
        next=button("下一张 ›"); next.setOnClickListener(v->move(1)); bar.addView(next);
        TextView hint=Ui.text(this,"左右滑动查看全部图片",11,0xff93a78e,false); hint.setGravity(Gravity.CENTER); hint.setPadding(0,0,0,dp(16)); root.addView(hint);
        message.setOnClickListener(v->load()); load();
    }
    private int total() { return assets!=null?assets.size():items==null?0:items.length(); }
    private boolean swipe(MotionEvent event) {
        if (event.getAction()==MotionEvent.ACTION_DOWN) { downX=event.getX(); downY=event.getY(); return true; }
        if (event.getAction()==MotionEvent.ACTION_UP) { float dx=event.getX()-downX,dy=event.getY()-downY; if (Math.abs(dx)>dp(48)&&Math.abs(dx)>Math.abs(dy)*1.3f) move(dx<0?1:-1); else if (image.getDrawable()==null) load(); return true; } return true;
    }
    private void move(int delta) { if (index+delta<0||index+delta>=total()) return; index+=delta; load(); }
    private Uri local(JSONObject item) {
        String uri=item.optString("localUri"); return uri.isEmpty()?((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).getUriForDownloadedFile(item.optLong("id")):Uri.parse(uri);
    }
    private void load() {
        if (destroyed||total()==0) return; final int token=++generation,page=index;
        if (request!=null) request.cancel(true); HttpURLConnection old=connection; if (old!=null) old.disconnect();
        image.setImageDrawable(null); message.setText("正在加载第 "+(index+1)+" 张图片…"); message.setVisibility(View.VISIBLE);
        count.setText((index+1)+" / "+total()); previous.setEnabled(index>0); previous.setAlpha(index>0?1:.4f); next.setEnabled(index+1<total()); next.setAlpha(index+1<total()?1:.4f);
        request=worker.submit(()->{
            try {
                Bitmap bitmap;
                if (info!=null) { File file=remote(page); bitmap=decode(file.getPath()); }
                else {
                    Uri uri=local(items.getJSONObject(page)); if (uri==null) throw new Exception("这张图片尚未下载完成或已移除，点击可重试。");
                    File file=new File(cache,"local_"+page); if (!cache.exists()&&!cache.mkdirs()) throw new Exception("无法创建预览缓存。");
                    try (InputStream input=getContentResolver().openInputStream(uri);FileOutputStream output=new FileOutputStream(file)) { if (input==null) throw new Exception("图片不可读取。"); copy(input,output); }
                    bitmap=decode(file.getPath()); file.delete();
                }
                if (bitmap==null) throw new Exception("无法显示这张图片，点击可重试。");
                handler.post(()->{ if (destroyed||token!=generation) { bitmap.recycle(); return; } image.setImageBitmap(bitmap); message.setVisibility(View.GONE); });
            } catch (Exception e) { handler.post(()->{ if (!destroyed&&token==generation) message.setText(e.getMessage()==null?"图片加载失败，点击可重试。":e.getMessage()); }); }
            finally { if (destroyed) remove(cache); }
        });
    }
    private File remote(int page) throws Exception {
        if (!cache.exists()&&!cache.mkdirs()) throw new Exception("无法创建预览缓存。");
        File file=new File(cache,"remote_"+page); if (file.isFile()&&file.length()>0) return file;
        // Keep only the current/adjacent cached pictures; gallery files are never modified.
        File[] files=cache.listFiles(); if (files!=null) for (File old:files) if (!old.getName().equals("remote_"+(page-1))&&!old.getName().equals("remote_"+(page+1))) old.delete();
        VideoResolver resolver=new VideoResolver(url->android.webkit.CookieManager.getInstance().getCookie(url),s->{});
        VideoResolver.Page media=resolver.probe(info,assets.get(page));
        HttpURLConnection c=(HttpURLConnection)new URL(media.url).openConnection(); connection=c;
        c.setInstanceFollowRedirects(false); c.setConnectTimeout(12000); c.setReadTimeout(15000);
        for (Map.Entry<String,String> header:PlayerSource.headers(info,media.url).entrySet()) if (!header.getKey().startsWith("android-")) c.setRequestProperty(header.getKey(),header.getValue());
        boolean done=false;
        try {
            if (c.getResponseCode()!=200) throw new Exception("图片地址已失效，请返回重新解析。");
            try (InputStream input=c.getInputStream();FileOutputStream output=new FileOutputStream(file)) { copy(input,output); }
            done=true; return file;
        } finally { c.disconnect(); connection=null; if (!done) file.delete(); }
    }
    private void copy(InputStream input,FileOutputStream output) throws Exception {
        byte[] buffer=new byte[16384]; int n; long size=0;
        while ((n=input.read(buffer))!=-1) { if (destroyed||Thread.currentThread().isInterrupted()) throw new InterruptedException(); size+=n; if (size>32*1024*1024L) throw new Exception("单张图片过大，请保存后在相册查看。"); output.write(buffer,0,n); }
    }
    private Bitmap decode(String file) {
        BitmapFactory.Options opts=new BitmapFactory.Options(); opts.inJustDecodeBounds=true; BitmapFactory.decodeFile(file,opts); opts.inSampleSize=1;
        while (Math.max(opts.outWidth,opts.outHeight)/opts.inSampleSize>2560) opts.inSampleSize*=2;
        opts.inJustDecodeBounds=false; return BitmapFactory.decodeFile(file,opts);
    }
    private void options() {
        Ui.Sheet sheet=Ui.sheet(this,"图文选项","同一条内容的图片与正文。","image").action("info","查看正文","标题、作者与原文",true,()->caption());
        if(info==null) {sheet.action("share","分享已保存的图片","按原顺序分享整组图片",()->share()).action("web","重新解析源链接","",()->{
                startActivity(new Intent(this,MainActivity.class).setAction(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,album.optString("source")).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP)); finish();
            });}sheet.show();
    }
    private void caption() {
        String description=info!=null?info.description:album.optString("description");
        if (!description.isEmpty()||info!=null) { showCaption(description); return; }
        JSONObject text=AlbumRecords.text(album); if (text==null) { showCaption(""); return; }
        worker.submit(()-> { String body=""; try (InputStream input=getContentResolver().openInputStream(local(text))) {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream(); byte[] buffer=new byte[4096]; int n;
            while (input!=null&&(n=input.read(buffer))>0&&bytes.size()<128*1024) bytes.write(buffer,0,n); body=new String(bytes.toByteArray(),java.nio.charset.StandardCharsets.UTF_8);
        } catch (Exception ignored) { } final String result=body; handler.post(()->{ if (!destroyed) showCaption(result); }); });
    }
    private void showCaption(String body) { Ui.sheet(this,"图文正文",body.isEmpty()?"这条内容没有可读取的正文。":body,"info").show(); }
    private void share() {
        ArrayList<Uri> uris=new ArrayList<>(); for (int i=0;i<items.length();i++) { Uri uri=local(items.optJSONObject(i)); if (uri!=null) uris.add(uri); }
        if (uris.isEmpty()) { showCaption("图片尚未保存完成。"); return; }
        Intent intent=new Intent(Intent.ACTION_SEND_MULTIPLE).setType("image/*").putParcelableArrayListExtra(Intent.EXTRA_STREAM,uris).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        ClipData clip=ClipData.newRawUri("images",uris.get(0)); for (int i=1;i<uris.size();i++) clip.addItem(new ClipData.Item(uris.get(i))); intent.setClipData(clip); startActivity(Intent.createChooser(intent,"分享图文图片"));
    }
    private static void remove(File folder) { if (folder==null) return; File[] files=folder.listFiles(); if (files!=null) for (File f:files) f.delete(); folder.delete(); }
    @Override protected void onSaveInstanceState(Bundle saved) { saved.putInt("index",index); super.onSaveInstanceState(saved); }
    @Override protected void onDestroy() { destroyed=true; generation++; handler.removeCallbacksAndMessages(null); if (request!=null) request.cancel(true); HttpURLConnection c=connection; if (c!=null) c.disconnect(); worker.shutdownNow(); remove(cache); if (image!=null) image.setImageDrawable(null); super.onDestroy(); }
}
