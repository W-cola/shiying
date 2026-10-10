package cn.shiying.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import cn.shiying.mobile.core.MediaHeaders;
import cn.shiying.mobile.core.Xiaohongshu;
import cn.shiying.mobile.core.Platforms;
import cn.shiying.mobile.core.Bilibili;
import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private DownloadManager downloads;
    private SharedPreferences preferences;
    private LinearLayout root, mainContainer, home, library, nav, result, recentRows, libraryRows, progressCard;
    private TextView parseButton, note, recentCount, downloadButton, audioButton, progressText, progressDetail, cancelDownload, homeTab, libraryTab,librarySummary;
    private EditText input;
    private ScrollView homeScroll;
    private ProgressBar progress;
    private VideoInfo video;
    private int selectedFormat, revision, selectedTab;
    private boolean loading, active, destroyed, restoring;
    private Future<?> request;
    private JSONArray records = new JSONArray();
    private WebView browser;
    private View browserPanel;
    private TextView browserStatus;
    private String browserSource = "", browserTarget = "";
    private boolean browserReading;
    private boolean browserReturnAttempted;
    private long activeDownload = -1;
    private boolean preparingAudio;
    private int libraryFilter;
    private String libraryQuery="";
    private final java.util.Set<Long> deletingGroups=new java.util.HashSet<>();

    private int dp(float n) { return Ui.dp(this, n); }
    private LinearLayout column() { LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.VERTICAL); return l; }
    private LinearLayout row() { LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.HORIZONTAL); l.setGravity(Gravity.CENTER_VERTICAL); return l; }
    private LinearLayout.LayoutParams params(int w, int h) { return new LinearLayout.LayoutParams(w < 0 ? w : dp(w), h < 0 ? h : dp(h)); }
    private void gap(LinearLayout parent, int n) { View space = new View(this); parent.addView(space, params(1,n)); }
    private TextView text(String s, int size, int color, boolean medium) { return Ui.text(this,s,size,color,medium); }
    private TextView button(String s, int color, int background) {
        TextView v = text(s,15,color,true); v.setGravity(Gravity.CENTER); v.setMinHeight(dp(48));
        v.setPadding(dp(16),0,dp(16),0); Ui.ripple(v,background,16); v.setClickable(true); v.setFocusable(true); return v;
    }
    private ScrollView scroll(LinearLayout content) {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setClipToPadding(false);
        scroll.setVerticalScrollBarEnabled(false); scroll.addView(content, new ScrollView.LayoutParams(-1,-2)); return scroll;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        downloads = (DownloadManager)getSystemService(DOWNLOAD_SERVICE);
        preferences = getSharedPreferences("shiying", MODE_PRIVATE);
        records=RecordStore.read(this);
        if(state!=null){libraryFilter=state.getInt("filter");libraryQuery=state.getString("query","");selectedFormat=state.getInt("format");}
        for (int i=0;i<records.length();i++) { JSONObject r=records.optJSONObject(i); if (r!=null) { r.remove("checking"); r.remove("deleting"); } }
        getWindow().setStatusBarColor(Color.TRANSPARENT); getWindow().setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        root = column(); root.setBackgroundColor(Ui.BG); setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int bottom = insets.getSystemWindowInsetBottom();
            if (Build.VERSION.SDK_INT >= 30) {
                boolean ime = insets.isVisible(WindowInsets.Type.ime());
                bottom = Math.max(insets.getInsets(WindowInsets.Type.systemBars()).bottom, insets.getInsets(WindowInsets.Type.ime()).bottom);
                if (nav != null) nav.setVisibility(ime || browser!=null ? View.GONE : View.VISIBLE);
            }
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), bottom);
            return insets;
        });
        mainContainer = column(); root.addView(mainContainer,new LinearLayout.LayoutParams(-1,0,1));
        buildHome(); buildLibrary(); buildNavigation();
        if (state != null) {
            restoring = true; input.setText(state.getString("input", ""));
            try { String json = state.getString("video", ""); if (!json.isEmpty()) setVideo(VideoInfo.fromJson(new JSONObject(json))); } catch (Exception ignored) { }
            restoring=false;
            switchTab(state.getInt("tab",0));
        }
        if(state==null)handleIntent(getIntent()); refreshDownloads();
    }

    private void buildHome() {
        home = column(); home.setPadding(dp(22),dp(20),dp(22),dp(18));
        LinearLayout brand = row();
        Ui.Icon logo = new Ui.Icon(this,"logo",Ui.GREEN); brand.addView(logo,params(29,29));
        TextView name = text("拾影",23,Ui.INK,true); LinearLayout.LayoutParams np = params(-2,-2); np.leftMargin=dp(9); brand.addView(name,np);
        View fill = new View(this); brand.addView(fill,new LinearLayout.LayoutParams(0,1,1));
        TextView local = text("●  本地保存",11,Ui.GREEN,true); local.setPadding(dp(11),dp(7),dp(11),dp(7));
        local.setBackground(Ui.shape(0xffe9f0e1,14,0,this)); brand.addView(local); home.addView(brand);
        gap(home,26);
        FrameLayout hero = new FrameLayout(this);
        LinearLayout words = column();
        TextView eyebrow = text("KEEP WHAT MOVES YOU",10,Ui.MUTED,true); eyebrow.setLetterSpacing(.12f); words.addView(eyebrow);
        gap(words,10);
        TextView headline = text("喜欢的片段，\n随时留在身边。",28,Ui.INK,true); headline.setLineSpacing(dp(5),1); words.addView(headline);
        gap(words,11); words.addView(text("留住瞬间，也留住灵感。",12,Ui.MUTED,false));
        hero.addView(words,new FrameLayout.LayoutParams(-1,-2));
        if (getResources().getConfiguration().screenWidthDp >= 400&&getResources().getConfiguration().fontScale<=1.15f) {
            FrameLayout.LayoutParams ap = new FrameLayout.LayoutParams(dp(108),dp(134),Gravity.RIGHT|Gravity.TOP); ap.topMargin=dp(10);
            hero.addView(new Ui.Artwork(this),ap);
        }
        home.addView(hero,params(-1,146)); gap(home,20);

        LinearLayout form = column(); form.setPadding(dp(18),dp(18),dp(18),dp(18)); form.setBackground(Ui.shape(Ui.WHITE,26,Ui.LINE,this));
        LinearLayout heading = row(); heading.addView(text("添加一个视频",17,Ui.INK,true),new LinearLayout.LayoutParams(0,-2,1));
        TextView clear=text("清空",13,0xff865b4c,true); clear.setGravity(Gravity.CENTER); Ui.ripple(clear,0xfff5eee8,12);
        LinearLayout.LayoutParams clearParams=params(56,48); clearParams.rightMargin=dp(8); heading.addView(clear,clearParams);
        clear.setContentDescription("清空分享链接和解析结果"); clear.setOnClickListener(v -> clearInput());
        TextView paste = text("粘贴",13,Ui.GREEN,true); paste.setGravity(Gravity.CENTER); Ui.ripple(paste,0xffeff4e7,12);
        heading.addView(paste,params(64,48)); paste.setContentDescription("从剪贴板粘贴分享文字"); paste.setOnClickListener(v -> paste()); form.addView(heading);
        gap(form,14);
        input = new EditText(this); input.setTextColor(Ui.INK); input.setHintTextColor(Ui.MUTED); input.setTextSize(14);
        input.setTypeface(android.graphics.Typeface.create("sans-serif",0)); input.setGravity(Gravity.TOP|Gravity.LEFT);
        input.setHint("粘贴分享文字、视频或图文链接\n抖音 · 小红书 · B站 · 快手 · 视频号"); input.setBackground(null);
        input.setPadding(0,dp(4),0,dp(8)); input.setMinLines(3); input.setMaxLines(5);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        form.addView(input,params(-1,108));
        input.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s,int start,int count,int after) { }
            public void onTextChanged(CharSequence s,int start,int before,int count) {
                if (restoring) return;
                revision++; video = null; result.setVisibility(View.GONE);
                if (loading) { loading=false; preparingAudio=false; if (request != null) request.cancel(true); }
                updateParseButton();
            }
            public void afterTextChanged(Editable e) { }
        });
        parseButton = button("解析视频  →",Ui.WHITE,Ui.GREEN); form.addView(parseButton,params(-1,54));
        parseButton.setOnClickListener(v -> resolve()); home.addView(form);
        TextView assist = text("需要登录？试试浏览器辅助解析",12,Ui.MUTED,false); assist.setGravity(Gravity.CENTER); assist.setMinHeight(dp(48));
        assist.setOnClickListener(v -> openAssistFromInput()); home.addView(assist,params(-1,48));
        note = text("",12,Ui.MUTED,false); note.setLineSpacing(dp(3),1); note.setVisibility(View.GONE); home.addView(note);
        result = column(); result.setVisibility(View.GONE); result.setBackground(Ui.shape(Ui.WHITE,24,Ui.LINE,this));
        result.setPadding(dp(18),dp(18),dp(18),dp(18)); home.addView(result);
        progressCard = column(); progressCard.setVisibility(View.GONE); progressCard.setBackground(Ui.shape(0xffeaf1e1,20,0,this));
        progressCard.setPadding(dp(16),dp(16),dp(16),dp(16)); home.addView(progressCard);
        LinearLayout pr = row(); progressText=text("正在下载",15,Ui.GREEN,true); pr.addView(progressText,new LinearLayout.LayoutParams(0,-2,1));
        cancelDownload=text("取消",13,Ui.MUTED,true); cancelDownload.setMinHeight(dp(48)); cancelDownload.setGravity(Gravity.CENTER); cancelDownload.setPadding(dp(10),dp(8),dp(10),dp(8));
        cancelDownload.setOnClickListener(v -> cancelActiveDownload()); pr.addView(cancelDownload); progressCard.addView(pr);
        gap(progressCard,8); progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal); progress.setMax(1000);
        progress.setProgressTintList(ColorStateList.valueOf(Ui.GREEN)); progress.setProgressBackgroundTintList(ColorStateList.valueOf(0xffd6e3c9));
        progressCard.addView(progress,params(-1,6)); gap(progressCard,10);
        progressDetail=text("下载会在后台继续",12,Ui.MUTED,false); progressCard.addView(progressDetail);
        gap(home,22);
        LinearLayout recent=row(); recent.addView(text("最近收下的片段",16,Ui.INK,true),new LinearLayout.LayoutParams(0,-2,1));
        recentCount=text("0 个",12,Ui.MUTED,false); recent.addView(recentCount); home.addView(recent); gap(home,14);
        recentRows=column(); home.addView(recentRows);
        TextView footer=text("视频 / 图片 → 相册 · 拾影 　音频 → 音乐 · 拾影\n只在你主动解析时访问视频网站。",11,Ui.MUTED,false);
        footer.setGravity(Gravity.CENTER); footer.setLineSpacing(dp(4),1); gap(home,24); home.addView(footer);
        homeScroll=scroll(home); mainContainer.addView(homeScroll,params(-1,-1));
    }

    private void buildLibrary() {
        library=column(); library.setPadding(dp(24),dp(24),dp(24),dp(24));
        LinearLayout title=row(); title.addView(text("我的片段",28,Ui.INK,true),new LinearLayout.LayoutParams(0,-2,1));
        TextView settings=text("管理",13,Ui.MUTED,true); settings.setMinWidth(dp(48));settings.setMinHeight(dp(48));settings.setGravity(Gravity.CENTER);settings.setPadding(dp(8),dp(12),dp(8),dp(12)); settings.setOnClickListener(v -> showSettings()); title.addView(settings);
        library.addView(title); gap(library,9); library.addView(text("画面、声音、灵感，都在这里。",13,Ui.MUTED,false)); gap(library,20);
        EditText search=new EditText(this); search.setSingleLine(true); search.setTextSize(14); search.setTextColor(Ui.INK); search.setHintTextColor(Ui.MUTED); search.setHint("搜索标题或作者"); search.setContentDescription("搜索已保存的片段"); search.setPadding(dp(16),0,dp(16),0); search.setBackground(Ui.shape(Ui.WHITE,18,Ui.LINE,this)); library.addView(search,params(-1,52));
        search.setText(libraryQuery);search.addTextChangedListener(new TextWatcher(){ public void beforeTextChanged(CharSequence s,int st,int count,int after){} public void onTextChanged(CharSequence s,int st,int before,int count){ libraryQuery=s.toString(); refreshDownloads(); } public void afterTextChanged(Editable e){} });
        gap(library,14); LinearLayout filters=row(); String[] labels={"全部","视频","图文","音频"};
        for(int i=0;i<labels.length;i++){ final int index=i; TextView chip=button(labels[i],i==libraryFilter?Ui.WHITE:Ui.GREEN,i==libraryFilter?Ui.GREEN:Ui.SOFT);chip.setSelected(i==libraryFilter); chip.setPadding(dp(4),0,dp(4),0); chip.setTextSize(13); LinearLayout.LayoutParams fp=new LinearLayout.LayoutParams(0,dp(48),1); if(i>0)fp.leftMargin=dp(8); filters.addView(chip,fp); chip.setOnClickListener(v->{ libraryFilter=index; for(int j=0;j<filters.getChildCount();j++){TextView child=(TextView)filters.getChildAt(j);Ui.ripple(child,j==index?Ui.GREEN:Ui.SOFT,16);child.setTextColor(j==index?Ui.WHITE:Ui.GREEN);child.setSelected(j==index);} refreshDownloads(); }); }
        library.addView(filters); gap(library,18); librarySummary=text("",12,Ui.MUTED,false); library.addView(librarySummary); gap(library,8);
        libraryRows=column(); library.addView(libraryRows);
        ScrollView sc=scroll(library); sc.setVisibility(View.GONE); mainContainer.addView(sc,params(-1,-1));
    }

    private void buildNavigation() {
        nav=row(); nav.setBackground(Ui.shape(Ui.WHITE,0,0,this)); nav.setPadding(dp(34),dp(9),dp(34),dp(9));
        homeTab=button("收下视频",Ui.GREEN,0xffe8f1dc); libraryTab=button("我的片段",Ui.MUTED,Ui.WHITE); homeTab.setTextSize(13);libraryTab.setTextSize(13);Ui.decorate(homeTab,"download",Ui.GREEN);Ui.decorate(libraryTab,"library",Ui.GREEN);
        nav.addView(homeTab,new LinearLayout.LayoutParams(0,dp(48),1)); LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(48),1); p.leftMargin=dp(16); nav.addView(libraryTab,p);
        homeTab.setOnClickListener(v -> switchTab(0)); libraryTab.setOnClickListener(v -> switchTab(1)); root.addView(nav,params(-1,68));
    }

    private void switchTab(int index) {
        boolean changed=selectedTab!=index;
        selectedTab=index; mainContainer.getChildAt(0).setVisibility(index==0?View.VISIBLE:View.GONE);
        mainContainer.getChildAt(1).setVisibility(index==1?View.VISIBLE:View.GONE);
        Ui.ripple(homeTab,index==0?0xffe8f1dc:Ui.WHITE,16); homeTab.setTextColor(index==0?Ui.GREEN:Ui.MUTED);
        Ui.ripple(libraryTab,index==1?0xffe8f1dc:Ui.WHITE,16); libraryTab.setTextColor(index==1?Ui.GREEN:Ui.MUTED);
        homeTab.setSelected(index==0); libraryTab.setSelected(index==1); if(changed) Ui.appear(mainContainer.getChildAt(index));
        refreshDownloads();
    }

    private void paste() {
        ClipboardManager clipboard=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
        if (clipboard.hasPrimaryClip() && clipboard.getPrimaryClip().getItemCount()>0) {
            CharSequence content=clipboard.getPrimaryClip().getItemAt(0).coerceToText(this);
            input.setText(content); input.setSelection(input.length());
        } else toast("剪贴板里还没有分享链接。");
    }

    private void clearInput() {
        revision++; if (request!=null) { request.cancel(true); request=null; }
        loading=false; preparingAudio=false; video=null; selectedFormat=0; input.setText(""); result.removeAllViews(); result.setVisibility(View.GONE);
        if (getIntent()!=null) getIntent().removeExtra(Intent.EXTRA_TEXT);
        updateParseButton(); status("",false); hideKeyboard(); homeScroll.smoothScrollTo(0,0);
    }

    private void updateParseButton() { if (parseButton!=null) { parseButton.setText(loading?(preparingAudio?"正在准备音频…":"正在解析…"):"解析视频  →"); parseButton.setEnabled(!loading); parseButton.setAlpha(loading?.65f:1f); } }
    private void status(String s, boolean error) {
        if (destroyed) return; note.setText(s); note.setTextColor(error?0xffa05d39:Ui.MUTED); note.setVisibility(s.isEmpty()?View.GONE:View.VISIBLE);
    }
    private VideoResolver resolver() { final int token=revision; return new VideoResolver(new VideoResolver.Cookies() {
        public String get(String url) { return CookieManager.getInstance().getCookie(url); }
        public void save(String url,String value) { CookieManager.getInstance().setCookie(url,value); }
    }, s -> handler.post(() -> { if (token==revision&&!destroyed) status(s,false); })); }
    private void hideKeyboard() { ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(input.getWindowToken(),0); input.clearFocus(); }

    private void resolve() {
        if (loading) return;
        String value=input.getText().toString();
        try { VideoResolver.link(value); } catch (Exception e) { status(e.getMessage(),true); return; }
        hideKeyboard(); loading=true; updateParseButton(); status("正在解析分享链接…",false); result.setVisibility(View.GONE);
        final int token=++revision;
        request=executor.submit(() -> {
            try {
                VideoInfo info=resolver().resolve(value);
                handler.post(() -> { if (token!=revision||destroyed) return; loading=false; updateParseButton(); setVideo(info); status("解析完成，选择画质即可保存。",false); });
            } catch (VideoResolver.NeedsBrowser e) {
                handler.post(() -> {
                    if (token!=revision||destroyed) return; loading=false; updateParseButton(); status(e.getMessage(),false);
                    if (Platforms.known(e.url)) {
                        String target=VideoResolver.isDouyin(e.url)&&!e.id.isEmpty()?"https://www.douyin.com/video/"+e.id:e.url;
                        showBrowser(target,e.id,value); browserStatus.setText("正在读取目标内容。如需登录或验证，请手动完成；读取后会返回保存页面。");
                        return;
                    }
                    Ui.sheet(this,"让播放器帮忙读取",e.getMessage(),"web").action("web","打开浏览器","手动完成登录或验证",true,()->showBrowser(e.url,e.id,value)).action("close","稍后","",()->{}).show();
                });
            } catch (Exception e) { handler.post(() -> { if (token!=revision||destroyed) return; loading=false; updateParseButton(); status(friendly(e),true); }); }
        });
    }

    private void setVideo(VideoInfo info) {
        video=info; selectedFormat=restoring?Math.max(0,Math.min(info.formats.size()-1,selectedFormat)):0; result.removeAllViews(); result.setVisibility(View.VISIBLE);
        LinearLayout top=row(); FrameLayout cover=new FrameLayout(this); cover.setBackground(Ui.shape(0xffedf3e4,14,0,this)); cover.setClipToOutline(true);
        Ui.Icon icon=new Ui.Icon(this,"mini",Ui.GREEN); FrameLayout.LayoutParams icp=new FrameLayout.LayoutParams(dp(32),dp(32),Gravity.CENTER); cover.addView(icon,icp);
        ImageView image=new ImageView(this); image.setScaleType(ImageView.ScaleType.CENTER_CROP); cover.addView(image,new FrameLayout.LayoutParams(-1,-1));
        top.addView(cover,params(66,78)); LinearLayout infoText=column(); infoText.setPadding(dp(14),0,0,0);
        TextView title=text(info.title,16,Ui.INK,true); title.setMaxLines(2); title.setEllipsize(android.text.TextUtils.TruncateAt.END); infoText.addView(title);
        gap(infoText,8); String meta=(info.author.isEmpty()?"视频":info.author)+"  ·  "+(info.isImages()?"图文 · "+info.imageCount()+" 张图片":duration(info.duration));
        infoText.addView(text(meta,11,Ui.MUTED,false)); top.addView(infoText,new LinearLayout.LayoutParams(0,-2,1)); result.addView(top);
        if (!info.thumbnail.isEmpty()) executor.submit(() -> {
            try {
                java.net.HttpURLConnection connection=(java.net.HttpURLConnection)new java.net.URL(info.thumbnail).openConnection();
                connection.setConnectTimeout(8000); connection.setReadTimeout(10000); connection.setRequestProperty("User-Agent",info.userAgent);
                try (InputStream stream=connection.getInputStream()) {
                    java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream(); byte[] part=new byte[8192]; int n;
                    while ((n=stream.read(part))>0&&buffer.size()<3*1024*1024) buffer.write(part,0,n);
                    byte[] bytes=buffer.toByteArray(); BitmapFactory.Options opts=new BitmapFactory.Options(); opts.inJustDecodeBounds=true;
                    BitmapFactory.decodeByteArray(bytes,0,bytes.length,opts); opts.inSampleSize=Math.max(1,Math.max(opts.outWidth,opts.outHeight)/400); opts.inJustDecodeBounds=false;
                    Bitmap bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length,opts);
                    handler.post(() -> { if (video==info&&!destroyed&&bitmap!=null) image.setImageBitmap(bitmap); });
                } finally { connection.disconnect(); }
            } catch (Exception ignored) { }
        });
        gap(result,18); result.addView(text("选择画质",11,Ui.MUTED,false)); gap(result,10);
        HorizontalScrollView qualityScroll=new HorizontalScrollView(this); qualityScroll.setHorizontalScrollBarEnabled(false); LinearLayout qualities=row();
        for (int i=0;i<info.formats.size();i++) {
            final int index=i; TextView choice=button(info.formats.get(i).label,i==selectedFormat?Ui.WHITE:Ui.GREEN,i==selectedFormat?Ui.GREEN:0xfff0f4ea);
            choice.setTextSize(13); choice.setMinHeight(dp(48)); LinearLayout.LayoutParams cp=params(-2,48); cp.rightMargin=dp(8); qualities.addView(choice,cp);
            choice.setOnClickListener(v -> {
                selectedFormat=index;
                for (int j=0;j<qualities.getChildCount();j++) { TextView item=(TextView)qualities.getChildAt(j); Ui.ripple(item,j==index?Ui.GREEN:0xfff0f4ea,16); item.setTextColor(j==index?Ui.WHITE:Ui.GREEN); }
            });
        }
        qualityScroll.addView(qualities); result.addView(qualityScroll); gap(result,16);
        downloadButton=button("↓  保存到手机",Ui.GREEN,Ui.LIME); downloadButton.setOnClickListener(v -> startDownload()); result.addView(downloadButton,params(-1,50));
        gap(result,10); TextView viewSource=button(info.isImages()?"▧  应用内预览":"▶  应用内播放",Ui.WHITE,Ui.GREEN); viewSource.setGravity(Gravity.CENTER); viewSource.setPadding(0,dp(8),0,dp(8));
        viewSource.setOnClickListener(v -> { try { if (info.isImages()) ImageActivity.open(this,info,selectedFormat); else PlayerActivity.open(this,info,selectedFormat); } catch (Exception e) { toast("无法打开预览，请重新解析。"); } }); result.addView(viewSource);
        if (!info.isImages()) {
            gap(result,22); LinearLayout audio=column(); audio.setPadding(dp(16),dp(16),dp(16),dp(16)); audio.setBackground(Ui.shape(Ui.SOFT,20,0,this)); LinearLayout audioTitle=row(); audioTitle.addView(new Ui.Icon(this,"audio",Ui.GREEN),params(26,26)); TextView audioName=text("只收下声音",17,Ui.INK,true); audioName.setPadding(dp(10),0,0,0); audioTitle.addView(audioName); audio.addView(audioTitle); gap(audio,9); audio.addView(text("原声音频 · 独立 M4A 文件\n用于剪辑、收藏，保存到音乐 / 拾影",12,Ui.MUTED,false)); gap(audio,14); audioButton=button("提取并保存音频",Ui.WHITE,Ui.GREEN); audioButton.setOnClickListener(v->startAudioDownload()); audio.addView(audioButton,params(-1,50)); result.addView(audio);
        }
        LinearLayout.LayoutParams rp=(LinearLayout.LayoutParams)result.getLayoutParams(); rp.bottomMargin=dp(16); result.setLayoutParams(rp);
        homeScroll.post(() -> { if (video==info&&!destroyed) homeScroll.smoothScrollTo(0,Math.max(0,result.getTop()-dp(16))); });
        Ui.appear(result);
    }

    private void startAudioDownload() {
        if (video==null||video.isImages()||loading) return;
        if (Build.VERSION.SDK_INT<=28&&checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)!=PackageManager.PERMISSION_GRANTED) { requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE},43); return; }
        final VideoInfo info=video; final VideoInfo.Format format=info.formats.get(selectedFormat); final int token=revision;
        loading=true; preparingAudio=true; updateParseButton(); if(audioButton!=null){audioButton.setEnabled(false);audioButton.setText("正在准备声音…");} status("正在确认音频来源…",false);
        request=executor.submit(()->{
            try { java.util.List<DownloadCoordinator.Prepared> parts=DownloadCoordinator.prepareAudio(resolver(),info,format);
                handler.post(()->{ if(token!=revision||destroyed)return; audioReady(); try { JSONArray created=CompoundDownloads.enqueueAudio(this,downloads,info,parts); JSONArray list=new JSONArray(); for(int i=0;i<created.length();i++)list.put(created.get(i)); for(int i=0;i<records.length()&&list.length()<300;i++)list.put(records.get(i)); records=list;saveRecords();refreshDownloads();status("音频任务已开始，完成后可在「我的片段」播放或分享。",false); } catch(Exception e){status(friendly(e),true);} });
            } catch(Exception e){handler.post(()->{if(token!=revision||destroyed)return;audioReady();status(friendly(e),true);});}
        });
    }
    private void audioReady(){loading=false;preparingAudio=false;updateParseButton();if(audioButton!=null){audioButton.setEnabled(true);audioButton.setText("提取并保存音频");}}

    private void startDownload() {
        if (video==null||loading) return;
        if (Build.VERSION.SDK_INT<=28&&checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)!=PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE},42); return;
        }
        final VideoInfo info=video; final VideoInfo.Format format=info.formats.get(selectedFormat); final int token=revision;
        loading=true; updateParseButton(); downloadButton.setEnabled(false); downloadButton.setAlpha(.6f); status("正在确认视频文件…",false);
        request=executor.submit(() -> {
            try {
                java.util.List<DownloadCoordinator.Prepared> media=DownloadCoordinator.prepare(resolver(),info,format);
                handler.post(() -> {
                    if (token!=revision||destroyed) return;
                    loading=false; updateParseButton(); downloadButton.setEnabled(true); downloadButton.setAlpha(1);
                    try {
                        JSONArray created=DownloadCoordinator.enqueue(this,downloads,info,media);
                        JSONArray list=new JSONArray(); for (int i=0;i<created.length();i++) list.put(created.get(i));
                        for (int i=0;i<records.length()&&list.length()<300;i++) list.put(records.get(i)); records=list; saveRecords();
                        status("下载已开始，完成后会出现在相册的「拾影」中。",false); refreshDownloads();
                    } catch (Exception e) { status(friendly(e),true); }
                });
            } catch (Exception e) { handler.post(() -> { if (token!=revision||destroyed) return; loading=false; updateParseButton(); downloadButton.setEnabled(true); downloadButton.setAlpha(1); status(friendly(e),true); }); }
        });
    }

    @Override public void onRequestPermissionsResult(int code,String[] names,int[] grants) {
        super.onRequestPermissionsResult(code,names,grants);
        if (code==42) { if (grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED) startDownload(); else status("保存到系统下载目录需要此存储权限。",true); }
        if (code==43) { if (grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED) startAudioDownload(); else status("保存音频到音乐目录需要此存储权限。",true); }
    }

    private void cancelActiveDownload() {
        if (activeDownload==-1) return;
        long id=activeDownload;
        JSONArray grouped=AlbumRecords.groups(records);
        for (int i=0;i<grouped.length();i++) { JSONObject group=grouped.optJSONObject(i); if (group!=null&&group.optLong("id")==id&&AlbumRecords.isAlbum(group)) { confirmDelete(group); return; } }
        Ui.sheet(this,"取消这个下载？","正在下载的临时文件会移除，你可以重新解析并下载。","download").action("trash","取消下载","移除这个任务的临时文件",()->{
                JSONObject record=null; for (int i=0;i<records.length();i++) if (records.optJSONObject(i)!=null&&records.optJSONObject(i).optLong("id")==id) record=records.optJSONObject(i);
                try { if (record!=null&&record.optBoolean("compound")) CompoundDownloads.cancel(this,id); else downloads.remove(id); } catch (Exception e) { toast("取消未完成，请重试。"); return; }
                mark(id,"下载已取消",true); activeDownload=-1; refreshDownloads();
            }).action("download","继续下载","",true,()->{}).show();
    }

    private void openAssistFromInput() {
        hideKeyboard(); try {
            String source=VideoResolver.link(input.getText().toString()); String id=VideoResolver.videoId(source);
            showBrowser(id.isEmpty()||!VideoResolver.isDouyin(source)?source:"https://www.douyin.com/video/"+id,id,source);
        } catch (Exception e) { status(e.getMessage(),true); }
    }

    private void showBrowser(String url,String target,String source) {
        if (browser!=null) return;
        try { browserSource=VideoResolver.link(source); } catch (Exception e) { browserSource=url; }
        browserTarget=target; browserReading=false; browserReturnAttempted=false;
        mainContainer.setVisibility(View.GONE); nav.setVisibility(View.GONE);
        LinearLayout panel=column(); panel.setBackgroundColor(Ui.BG); browserPanel=panel;
        LinearLayout toolbar=row(); toolbar.setPadding(dp(16),dp(12),dp(16),dp(12));
        TextView back=button("返回",Ui.GREEN,0xffe8f1dc); back.setMinHeight(dp(40)); back.setOnClickListener(v -> closeBrowser()); toolbar.addView(back,params(64,40));
        TextView title=text("浏览器辅助解析",15,Ui.INK,true); title.setGravity(Gravity.CENTER); toolbar.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        TextView scan=button("读取",Ui.WHITE,Ui.GREEN); scan.setMinHeight(dp(40)); scan.setOnClickListener(v -> readBrowser()); toolbar.addView(scan,params(64,40)); panel.addView(toolbar);
        browserStatus=text("请完成登录或验证，打开目标内容；视频播放后读取。",12,Ui.MUTED,false); browserStatus.setPadding(dp(20),dp(4),dp(20),dp(13)); panel.addView(browserStatus);
        browser=new WebView(this); browser.setBackgroundColor(Ui.WHITE); WebSettings s=browser.getSettings();
        s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setAllowFileAccess(false); s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW); s.setMediaPlaybackRequiresUserGesture(true);
        s.setUseWideViewPort(true); s.setLoadWithOverviewMode(true); s.setBuiltInZoomControls(true); s.setDisplayZoomControls(false);
        if (isDouyinOrKnown(url)) s.setUserAgentString(VideoResolver.DESKTOP_UA);
        CookieManager.getInstance().setAcceptCookie(true); CookieManager.getInstance().setAcceptThirdPartyCookies(browser,false);
        browser.setWebChromeClient(new WebChromeClient());
        browser.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view,String page,Bitmap icon) {
                if (Platforms.known(page)) view.evaluateJavascript(browserScript("browser_capture.js"),null);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req) {
                String scheme=req.getUrl().getScheme();
                if ("https".equals(scheme)) return false;
                browserStatus.setText("请留在网页中播放目标视频；应用外跳转已停止。"); return true;
            }
            @Override public void onPageFinished(WebView view,String page) {
                if (Platforms.known(page)) view.evaluateJavascript(browserScript("browser_capture.js"),null);
                if (browserTarget.isEmpty()) browserTarget=VideoResolver.videoId(page);
                browserStatus.setText("打开目标图文或播放视频后点击「读取」。登录或验证码需手动完成。"); handler.removeCallbacks(browserPoll); handler.postDelayed(browserPoll,1200);
            }
            @Override public void onPageCommitVisible(WebView view,String page) { if (Platforms.known(page)) view.evaluateJavascript(browserScript("browser_capture.js"),null); }
            @Override public void onReceivedSslError(WebView view,SslErrorHandler h,SslError error) { h.cancel(); browserStatus.setText("安全连接失败，请检查网络和系统时间。"); }
        });
        panel.addView(browser,new LinearLayout.LayoutParams(-1,0,1)); root.addView(panel,new LinearLayout.LayoutParams(-1,0,1)); browser.loadUrl(url);
    }

    private String browserScript(String name) {
        try (InputStream input=getAssets().open(name)) {
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream(); byte[] buffer=new byte[4096]; int n;
            while ((n=input.read(buffer))>0) bytes.write(buffer,0,n); return new String(bytes.toByteArray(),java.nio.charset.StandardCharsets.UTF_8);
        } catch (Exception e) { return "''"; }
    }

    private boolean isDouyinOrKnown(String s) { return Platforms.known(s); }
    private final Runnable browserPoll=new Runnable() { @Override public void run() { if (browser!=null&&active) { readBrowser(); handler.postDelayed(this,1800); } } };
    private void readBrowser() {
        if (browser==null||browserReading) return;
        browserReading=true;
        final WebView current=browser;
        String js=browserScript("browser_read.js");
        current.evaluateJavascript(js,value -> {
            if (browser!=current) { browserReading=false; return; }
            executor.submit(() -> {
                VideoInfo found=null; String pageMessage="";
                try {
                    Object decoded=new JSONTokener(value).nextValue();
                    JSONObject o=new JSONObject(String.valueOf(decoded)); String page=o.optString("page"), id=VideoResolver.videoId(page);
                    pageMessage=o.optString("platformMessage");
                    boolean douyin=VideoResolver.isDouyin(browserSource),xhs=Xiaohongshu.supports(browserSource);
                    boolean known=Platforms.known(browserSource);
                    if (known&&browserTarget.isEmpty()&&!id.isEmpty()) browserTarget=id;
                    boolean alias="B站".equals(Platforms.name(browserSource))&&browserTarget.startsWith("av")&&id.startsWith("BV");
                    boolean correct=!known||(!browserTarget.isEmpty()&&(browserTarget.equals(id)||alias)&&Platforms.samePlatform(browserSource,page));
                    if (xhs&&!correct&&!browserTarget.isEmpty()&&!browserReturnAttempted) {
                        String cookie=CookieManager.getInstance().getCookie("https://www.xiaohongshu.com/");
                        if (cookie!=null&&cookie.contains("web_session=")) {
                            browserReturnAttempted=true;
                            handler.post(() -> { if (browser==current&&!destroyed) current.loadUrl(browserSource); });
                        }
                    }
                    if (correct) {
                        JSONArray payloads=o.optJSONArray("payloads");
                        if (known&&payloads!=null) for (int i=0;i<payloads.length();i++) {
                            String body=payloads.optString(i); found=VideoResolver.fromJsonText(body,browserTarget,browserSource,page);
                            if (found==null) try { found=VideoResolver.fromJsonText(java.net.URLDecoder.decode(body.replace("+","%2B"),"UTF-8"),browserTarget,browserSource,page); } catch (Exception ignored) { }
                            if (found!=null) break;
                        }
                        String media=VideoResolver.mediaUrl(o.optString("url"));
                        if (found==null&&!known&&!media.isEmpty()&&!media.contains(".m3u8")&&o.optInt("width")>0&&o.optInt("height")>0) {
                            found=new VideoInfo(); found.sourceUrl=browserSource; found.pageUrl=page; found.id=browserTarget.isEmpty()?Long.toHexString(media.hashCode()&0xffffffffL):browserTarget;
                            found.title=o.optString("title","视频").replace(" - 抖音",""); found.thumbnail=o.optString("poster"); found.duration=o.optDouble("duration",0);
                            int w=o.optInt("width"),h=o.optInt("height"); found.formats.add(new VideoInfo.Format(media,w>0&&h>0?w+" × "+h:"当前播放画质",w,h,0));
                        }
                        if (found!=null) found.userAgent=o.optString("ua",VideoResolver.DESKTOP_UA);
                    }
                } catch (Exception ignored) { }
                final VideoInfo parsed=found;
                final String message=pageMessage;
                handler.post(() -> {
                    browserReading=false;
                    if (browser!=current||destroyed) return;
                    if (parsed!=null) { closeBrowser(); switchTab(0); setVideo(parsed); status("已读取目标内容，可以保存到手机。",false); }
                    else if (!message.isEmpty()) { browserStatus.setText(message); handler.removeCallbacks(browserPoll); }
                });
            });
        });
    }

    private void closeBrowser() {
        handler.removeCallbacks(browserPoll); CookieManager.getInstance().flush();
        if (browser!=null) { browser.stopLoading(); browser.destroy(); browser=null; }
        if (browserPanel!=null) { root.removeView(browserPanel); browserPanel=null; }
        mainContainer.setVisibility(View.VISIBLE); nav.setVisibility(View.VISIBLE); browserReading=false;
    }

    private void saveRecords() { RecordStore.save(this,records); }
    private void mark(long id,String error,boolean verified) {
        for (int i=0;i<records.length();i++) { JSONObject r=records.optJSONObject(i); if (r!=null&&r.optLong("id")==id) try { r.put("appError",error).put("verified",verified); } catch (Exception ignored) { } }
        saveRecords();
    }

    private int queryStatus(long id,long[] stats) {
        try (Cursor c=downloads.query(new DownloadManager.Query().setFilterById(id))) {
            if (c!=null&&c.moveToFirst()) {
                stats[0]=c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                stats[1]=c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                stats[2]=c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
                return c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
            }
        } catch (Exception ignored) { }
        return 0;
    }
    private int queryRecord(JSONObject record,long[] stats) {
        if (AlbumRecords.isAlbum(record)) {
            JSONArray items=record.optJSONArray("items"); int done=0,waiting=0,failed=0,images=0; boolean known=true;
            for (int i=0;items!=null&&i<items.length();i++) {
                JSONObject child=items.optJSONObject(i); if (child==null) continue; long[] part=new long[3]; int state=queryRecord(child,part);
                if (!child.optString("appError").isEmpty()) state=DownloadManager.STATUS_FAILED;
                stats[0]+=Math.max(0,part[0]); stats[1]+=Math.max(0,part[1]); known&=part[1]>0;
                if (state==DownloadManager.STATUS_SUCCESSFUL) { done++; if (child.optString("mime").startsWith("image/")) images++; }
                else if (state==DownloadManager.STATUS_PENDING||state==DownloadManager.STATUS_RUNNING||state==DownloadManager.STATUS_PAUSED) waiting++;
                else { failed++; stats[2]=part[2]; }
            }
            try { record.put("completedImages",images); } catch (Exception ignored) { }
            if (!known) stats[1]=-1;
            return waiting>0?DownloadManager.STATUS_RUNNING:failed>0?DownloadManager.STATUS_FAILED:done>0?DownloadManager.STATUS_SUCCESSFUL:0;
        }
        if (record.optBoolean("compound")) { CompoundDownloads.decorate(this,record); return CompoundDownloads.query(this,record,stats); }
        if (record.optString("localUri").isEmpty()) return queryStatus(record.optLong("id"),stats);
        try (android.content.res.AssetFileDescriptor descriptor=getContentResolver().openAssetFileDescriptor(Uri.parse(record.getString("localUri")),"r")) {
            if (descriptor==null) return 0;
            stats[0]=stats[1]=Math.max(record.optLong("bytes"),descriptor.getLength()); return DownloadManager.STATUS_SUCCESSFUL;
        } catch (Exception e) { return 0; }
    }
    private Uri recordUri(JSONObject record) { return record.optString("localUri").isEmpty()?downloads.getUriForDownloadedFile(record.optLong("id")):Uri.parse(record.optString("localUri")); }

    private void refreshDownloads() {
        if (recentRows==null||destroyed) return;
        recentRows.removeAllViews(); libraryRows.removeAllViews(); activeDownload=-1; int completed=0;
        for (int i=0;i<records.length();i++) {
            JSONObject record=records.optJSONObject(i); if (record==null) continue;
            long id=record.optLong("id"); long[] stats=new long[3]; int state=queryRecord(record,stats);
            if (!record.optString("appError").isEmpty()) state=DownloadManager.STATUS_FAILED;
            if (state==DownloadManager.STATUS_SUCCESSFUL) {
                if (!record.optBoolean("verified")&&!record.optBoolean("checking")) validateCompletion(record);
                if (!record.optBoolean("compound")&&(record.optString("mime","video/mp4").startsWith("video/")||record.optString("mime").startsWith("image/"))) MediaPublisher.publish(this,id,()->{});
            }
        }
        JSONArray visible=AlbumRecords.groups(records);
        for (int i=0;i<visible.length();i++) {
            JSONObject record=visible.optJSONObject(i); if (record==null) continue; long[] stats=new long[3]; int state=queryRecord(record,stats); long id=record.optLong("id");
            if (!record.optString("appError").isEmpty()) state=DownloadManager.STATUS_FAILED;
            if (state==DownloadManager.STATUS_SUCCESSFUL) completed++;
            else if (state==DownloadManager.STATUS_RUNNING||state==DownloadManager.STATUS_PENDING||state==DownloadManager.STATUS_PAUSED) {
                if (activeDownload==-1) { activeDownload=id; updateProgress(stats,state); if (AlbumRecords.isAlbum(record)) progressDetail.setText(record.optInt("completedImages")+" / "+record.optInt("imageCount")+" 张已保存  ·  后台继续下载");
                    if (record.optBoolean("compound")&&CompoundDownloads.job(this,id).optString("state").equals("assembling")) { boolean sound=record.optString("mime").startsWith("audio/"); progressText.setText(sound?"正在提取原声音频":"正在合并并保存至相册"); progressDetail.setText(sound?"下载已完成，正在保存到音乐 / 拾影。":"下载已完成，正在整理画面和声音。"); } }
            }
            if (i<3) recentRows.addView(recordView(record,state,stats,false));
            String mime=record.optString("mime"); boolean matches=libraryFilter==0||libraryFilter==1&&mime.startsWith("video/")||libraryFilter==2&&mime.startsWith("image/")||libraryFilter==3&&mime.startsWith("audio/");
            if(matches&&(libraryQuery.trim().isEmpty()||(record.optString("title")+" "+record.optString("author")).toLowerCase(Locale.ROOT).contains(libraryQuery.trim().toLowerCase(Locale.ROOT)))) libraryRows.addView(recordView(record,state,stats,true));
        }
        recentCount.setText(completed+" 个"); progressCard.setVisibility(activeDownload==-1?View.GONE:View.VISIBLE);
        if (records.length()==0) { recentRows.addView(emptyView(false)); libraryRows.addView(emptyView(true)); }
        else if(libraryRows.getChildCount()==0){ TextView empty=text("还没有匹配的片段\n试试其他分类或关键词",14,Ui.MUTED,false);empty.setGravity(Gravity.CENTER);empty.setPadding(0,dp(40),0,dp(40));libraryRows.addView(empty); }
        if(librarySummary!=null)librarySummary.setText("已收下 "+completed+" 条内容 · 视频 / 图文 / 音频");
    }

    private View emptyView(boolean full) {
        LinearLayout l=column(); l.setPadding(dp(20),dp(full?42:24),dp(20),dp(full?42:24)); l.setGravity(Gravity.CENTER); l.setBackground(Ui.shape(0xffedf2e6,20,0,this));
        if (full) { Ui.Icon icon=new Ui.Icon(this,"library",0xffabc396); l.addView(icon,params(40,40)); gap(l,18); }
        l.addView(text("你的第一段灵感，还在路上",13,Ui.GREEN,true)); gap(l,8);
        TextView sub=text("保存完成的视频会出现在这里",11,Ui.MUTED,false); sub.setGravity(Gravity.CENTER); l.addView(sub); return l;
    }

    private View recordView(JSONObject record,int state,long[] stats,boolean allowDelete) {
        LinearLayout outer=column(); LinearLayout line=row(); line.setPadding(dp(14),dp(16),dp(14),dp(16)); Ui.ripple(line,Ui.WHITE,22);
        Ui.Icon icon=new Ui.Icon(this,record.optString("mime").startsWith("audio/")?"audio":record.optString("mime").startsWith("image/")?"image":"mini",state==DownloadManager.STATUS_SUCCESSFUL?Ui.GREEN:Ui.MUTED); line.addView(icon,params(42,42));
        LinearLayout words=column(); words.setPadding(dp(13),0,dp(10),0); TextView title=text(record.optString("title","视频"),13,Ui.INK,true);
        title.setTextSize(14); title.setMaxLines(2); title.setEllipsize(android.text.TextUtils.TruncateAt.END); words.addView(title); gap(words,7);
        String status=state==DownloadManager.STATUS_SUCCESSFUL?size(stats[0])+" · 已保存":state==DownloadManager.STATUS_FAILED?"下载未完成 · 点击查看":state==0?"文件已移除":state==DownloadManager.STATUS_PAUSED?"等待网络继续下载":"正在下载 · "+size(stats[0]);
        if (AlbumRecords.isAlbum(record)) status="图文 · "+record.optInt("completedImages")+" / "+record.optInt("imageCount")+" 张"+(state==DownloadManager.STATUS_SUCCESSFUL?" · 已保存":state==DownloadManager.STATUS_RUNNING?" · 下载中":" · 部分图片未完成");
        else if(record.optString("mime").startsWith("audio/"))status="原声 · M4A · "+status;
        words.addView(text(status,11,Ui.MUTED,false)); line.addView(words,new LinearLayout.LayoutParams(0,-2,1));
        Ui.Icon action=new Ui.Icon(this,"arrow",Ui.MUTED);line.addView(action,params(18,18));
        if (allowDelete) {
            boolean deleting=record.optBoolean("deleting")||deletingGroups.contains(record.optLong("id"));
            TextView remove=text(deleting?"删除中":"删除",12,deleting?Ui.MUTED:0xff865b4c,true); remove.setGravity(Gravity.CENTER);
            Ui.ripple(remove,0xfff5eee8,12); remove.setContentDescription("删除片段："+record.optString("title","文件"));
            remove.setTag(record.optLong("id"));
            LinearLayout.LayoutParams deleteParams=params(48,48); deleteParams.leftMargin=dp(8); line.addView(remove,deleteParams);
            remove.setEnabled(!deleting); remove.setOnClickListener(v -> confirmDelete(record));
        }
        line.setOnClickListener(v -> showRecord(record)); line.setFocusable(true); outer.addView(line); gap(outer,10); return outer;
    }

    private void confirmDelete(JSONObject record) {
        if (record.optBoolean("deleting")||deletingGroups.contains(record.optLong("id"))) return;
        Ui.confirm(this,"删除这个片段？","“"+record.optString("title","文件")+"”\n\n"+(AlbumRecords.isAlbum(record)?"会删除这一条图文的全部 "+record.optInt("imageCount")+" 张图片、正文和相册条目。":"会删除下载记录及手机中的对应文件。")+"正在下载的任务会取消。","删除文件",()->deleteRecord(record));
    }

    private void deleteRecord(JSONObject record) {
        if (record.optBoolean("deleting")||deletingGroups.contains(record.optLong("id"))) return;
        if (AlbumRecords.isAlbum(record)) deletingGroups.add(record.optLong("id"));
        try { record.put("deleting",true); } catch (Exception ignored) { }
        refreshDownloads();
        executor.submit(()-> {
            String error="";
            try { RecordDeletion.delete(this,downloads,record); }
            catch (Exception e) { error=friendly(e); }
            final String failure=error;
            handler.post(()-> {
                record.remove("deleting"); deletingGroups.remove(record.optLong("id")); if (destroyed) return;
                if (AlbumRecords.isAlbum(record)) records=RecordStore.read(this);
                if (!failure.isEmpty()) { refreshDownloads(); Ui.notice(this,"文件尚未删除",failure+"\n\n记录已保留，可以重试。"); return; }
                long id=record.optLong("id"); JSONArray remaining=new JSONArray();
                for (int i=0;i<records.length();i++) { JSONObject item=records.optJSONObject(i); if (item!=null&&item.optLong("id")!=id) remaining.put(item); }
                records=remaining; saveRecords(); refreshDownloads(); toast("文件和记录已删除。");
            });
        });
    }

    private void updateProgress(long[] stats,int state) {
        boolean known=stats[1]>0; progress.setIndeterminate(!known); if (known) progress.setProgress((int)Math.min(1000,stats[0]*1000/stats[1]));
        progressText.setText(state==DownloadManager.STATUS_PAUSED?"等待网络":"正在收下这个片段"+(known?"  "+stats[0]*100/stats[1]+"%":""));
        progressDetail.setText(size(stats[0])+(known?" / "+size(stats[1]):"")+"  ·  后台继续下载");
    }

    private void validateCompletion(JSONObject record) {
        try { record.put("checking",true); } catch (Exception ignored) { }
        final long id=record.optLong("id");
        executor.submit(() -> {
            String error="";
            try {
                Uri uri=downloads.getUriForDownloadedFile(id); if (uri==null) throw new Exception("文件不存在");
                try (InputStream stream=getContentResolver().openInputStream(uri)) {
                    byte[] header=new byte[64]; int n=stream.read(header);
                    String expected=record.optString("mime","video/mp4").startsWith("image/")?"image":"video";
                    if (MediaHeaders.detect(header,Math.max(0,n),expected)==null) error="返回的内容不是预期媒体文件，请重新解析";
                }
            } catch (Exception e) { error="文件不可读取或已移除"; }
            final String message=error;
            handler.post(() -> { if (destroyed) return; try { record.remove("checking"); record.put("verified",true); if (!message.isEmpty()) record.put("appError",message); } catch (Exception ignored) { }
                if (!message.isEmpty()) downloads.remove(id); saveRecords(); refreshDownloads(); });
        });
    }

    private void showRecord(JSONObject record) {
        if (AlbumRecords.isAlbum(record)) { ImageActivity.open(this,record); return; }
        long[] stats=new long[3]; int state=queryRecord(record,stats); String mime=record.optString("mime","video/mp4");
        if (state==DownloadManager.STATUS_SUCCESSFUL&&record.optString("appError").isEmpty()) {
            String what=mime.startsWith("video/")?"视频":mime.startsWith("audio/")?"音频":mime.startsWith("image/")?"图片":"正文";
            String folder=record.optString("directory","Download");String location=(folder.equals("Music")?"音乐":folder.equals("Movies")||folder.equals("Pictures")?"相册":"下载")+" · 拾影";
            Ui.Sheet sheet=Ui.sheet(this,record.optString("title"),what+" · "+size(stats[0])+" · 已保存\n"+location,mime.startsWith("audio/")?"audio":mime.startsWith("image/")?"image":"mini");
            sheet.action(mime.startsWith("audio/")?"audio":"mini",(what.equals("视频")||what.equals("音频")?"播放":"查看")+what,"在拾影中打开",true,()->{
                Uri uri=recordUri(record); if(uri==null){toast("文件已移除。");return;}
                try { if(mime.startsWith("video/"))PlayerActivity.open(this,uri,record.optString("title")); else if(mime.startsWith("audio/"))AudioActivity.open(this,uri,record.optString("title")); else if(mime.startsWith("image/"))ImageActivity.open(this,new JSONObject().put("title",record.optString("title")).put("items",new JSONArray().put(record))); else startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(uri,mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)); }catch(Exception e){toast("文件无法打开，请检查是否已被移除。");}
            });
            sheet.action("share","分享"+what,"发送给其他应用",()->{
                Uri uri=recordUri(record);if(uri==null){toast("文件已移除。");return;}
                Intent share=new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);share.setClipData(ClipData.newRawUri("media",uri));startActivity(Intent.createChooser(share,"分享这个片段"));
            });
            if(mime.startsWith("video/"))sheet.action("audio","提取原声音频","从已保存的视频提取，无需再次下载",()->extractSavedAudio(record));
            sheet.action("paste","复制标题","",()->{((ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("标题",record.optString("title")));toast("标题已复制。");});
            sheet.action("web","重新解析源链接","回到原分享内容",()->{input.setText(record.optString("source"));switchTab(0);homeScroll.smoothScrollTo(0,0);});
            sheet.action("trash","删除片段","同时移除手机中的文件",()->confirmDelete(record));sheet.show();
        } else {
            String msg=record.optString("appError");if(msg.isEmpty())msg=state==0?"文件或下载任务已被移除。":state==DownloadManager.STATUS_FAILED?downloadReason(stats[2]):"下载由系统管理，网络恢复后会继续。";
            Ui.sheet(this,"下载详情",msg,"info").action("web","重新解析","刷新来源后重新保存",true,()->{input.setText(record.optString("source"));switchTab(0);}).show();
        }
    }
    private void extractSavedAudio(JSONObject record) {
        if(Build.VERSION.SDK_INT<=28&&checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)!=PackageManager.PERMISSION_GRANTED){toast("请先在首页保存一次音频，并允许存储权限。");return;}
        Uri uri=recordUri(record); if(uri==null){toast("原视频已移除。");return;}
        try { JSONObject created=CompoundDownloads.enqueueLocalAudio(this,record,uri); JSONArray list=new JSONArray().put(created);for(int i=0;i<records.length()&&list.length()<300;i++)list.put(records.get(i));records=list;saveRecords();CompoundDownloads.schedule(this,created.getLong("id"));refreshDownloads();toast("正在提取原声，完成后会出现在音频分类。"); }catch(Exception e){toast(friendly(e));}
    }
    private void showSettings() {
        Ui.sheet(this,"拾影 · 本地优先","把画面和声音收进自己的灵感库。","logo")
            .action("info","查看使用说明","支持的平台、保存位置与隐私说明",()->Ui.notice(this,"把片段收进手机","粘贴分享文字，点击解析。视频可在应用内播放、保存到相册；图文可左右滑动，按一条内容保存与删除。视频结果中的音频可单独提取为 M4A，保存在音乐 / 拾影。已保存视频也可从详情面板提取声音。\n\n支持抖音、小红书、B站、快手和可访问的视频号分享内容。遇到登录或验证，可用内置浏览器手动完成。视频号 sph 链接会发送给第三方在线解析服务；无需微信或元宝登录。直播、付费限制、DRM 和无法正常访问的内容不支持。\n\n链接、下载记录和网页会话保存在本机，无广告或分析统计。删除片段会同时删除实际文件。请使用自己拥有或已获授权的内容。"))
            .action("web","清除浏览器登录会话","下载记录和文件会保留",()->Ui.sheet(this,"清除浏览器会话？","会退出本应用内网页的登录状态。","web").action("check","清除","仅清除网页会话",true,()->CookieManager.getInstance().removeAllCookies(v->{CookieManager.getInstance().flush();android.webkit.WebStorage.getInstance().deleteAllData();toast("浏览器会话已清除。");})).action("close","保留","",()->{}).show())
            .action("library","查看系统下载目录","视频 / 图片在相册，音频在音乐",()->{try{startActivity(new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS));}catch(Exception e){toast("请在文件管理器中打开 拾影 保存目录。");}}).show();
    }

    private String friendly(Exception e) { if (e instanceof java.net.SocketTimeoutException) return "连接超时，请检查网络后重试。"; if (e instanceof java.net.UnknownHostException) return "无法连接网站，请检查手机网络。"; return e.getMessage()==null?"操作未完成，请重试。":e.getMessage(); }
    private static String size(long bytes) { if (bytes<=0) return "0 MB"; if (bytes<1024*1024) return String.format(Locale.ROOT,"%.0f KB",bytes/1024.0); return String.format(Locale.ROOT,"%.1f MB",bytes/(1024.0*1024)); }
    private static String duration(double seconds) { if (seconds<=0) return "时长未知"; return String.format(Locale.ROOT,"%02d:%02d",(int)seconds/60,(int)seconds%60); }
    private static String downloadReason(long code) { if (code==DownloadManager.ERROR_INSUFFICIENT_SPACE) return "手机空间不足，请释放存储后重试。"; if (code==DownloadManager.ERROR_HTTP_DATA_ERROR||code==403||code==404) return "视频地址可能过期，请重新解析。"; return "下载未完成（系统状态 "+code+"），请检查网络并重新解析。"; }
    private void toast(String s) { Toast.makeText(this,s,Toast.LENGTH_SHORT).show(); }
    private void handleIntent(Intent intent) { if (intent!=null&&Intent.ACTION_SEND.equals(intent.getAction())) { String content=intent.getStringExtra(Intent.EXTRA_TEXT); if (content!=null) { input.setText(content); switchTab(0); homeScroll.post(() -> homeScroll.smoothScrollTo(0,0)); status("已接收分享链接，点击解析即可。",false); } } }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); if (browser!=null) closeBrowser(); handleIntent(intent); }
    @Override public void onBackPressed() { if (browser!=null) closeBrowser(); else if (selectedTab==1) switchTab(0); else super.onBackPressed(); }
    private final Runnable poll=new Runnable() { public void run() { if (active&&!destroyed) { if (activeDownload!=-1) refreshDownloads(); handler.postDelayed(this,1300); } } };
    @Override protected void onResume() { super.onResume(); active=true; CompoundDownloads.recover(this); refreshDownloads(); handler.removeCallbacks(poll); handler.post(poll); if (browser!=null) { browser.onResume(); handler.removeCallbacks(browserPoll); handler.postDelayed(browserPoll,1000); } }
    @Override protected void onPause() { active=false; handler.removeCallbacks(poll); handler.removeCallbacks(browserPoll); if (browser!=null) browser.onPause(); super.onPause(); }
    @Override protected void onSaveInstanceState(Bundle state) { state.putString("input",input.getText().toString()); state.putInt("tab",selectedTab);state.putInt("filter",libraryFilter);state.putString("query",libraryQuery);state.putInt("format",selectedFormat); if (video!=null) try { state.putString("video",video.toJson().toString()); } catch (Exception ignored) { } super.onSaveInstanceState(state); }
    @Override protected void onDestroy() { destroyed=true; revision++; handler.removeCallbacksAndMessages(null); if (request!=null) request.cancel(true); if (browser!=null) browser.destroy(); executor.shutdownNow(); super.onDestroy(); }
}
