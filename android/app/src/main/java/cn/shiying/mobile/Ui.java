package cn.shiying.mobile;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.view.View;
import android.widget.TextView;
import android.app.Activity;
import android.app.Dialog;
import android.app.AlertDialog;
import android.animation.ObjectAnimator;
import android.animation.StateListAnimator;
import android.animation.ValueAnimator;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.view.animation.PathInterpolator;
import android.widget.LinearLayout;
import android.widget.ScrollView;

final class Ui {
    static final int BG = Color.rgb(246,248,242), INK = Color.rgb(32,58,42), GREEN = Color.rgb(36,75,54),
        MUTED = Color.rgb(92,112,95), LIME = Color.rgb(222,241,181), LINE = Color.rgb(226,233,220), WHITE = Color.WHITE;
    static final int SOFT=0xffedf3e8, DANGER=0xff9b443e;
    static boolean motion() { return ValueAnimator.areAnimatorsEnabled(); }
    static void appear(View v) { v.animate().cancel(); v.setAlpha(motion()?0:1); v.setTranslationY(motion()?dp(v.getContext(),12):0); if (motion()) v.animate().alpha(1).translationY(0).setDuration(240).setInterpolator(new PathInterpolator(.2f,0,0,1)).start(); }
    static void press(View v) {
        StateListAnimator states=new StateListAnimator();
        android.animation.AnimatorSet down=new android.animation.AnimatorSet(); down.playTogether(ObjectAnimator.ofFloat(v,"scaleX",.985f),ObjectAnimator.ofFloat(v,"scaleY",.985f)); down.setDuration(motion()?90:0);
        android.animation.AnimatorSet up=new android.animation.AnimatorSet(); up.playTogether(ObjectAnimator.ofFloat(v,"scaleX",1f),ObjectAnimator.ofFloat(v,"scaleY",1f)); up.setDuration(motion()?180:0);
        states.addState(new int[]{android.R.attr.state_pressed},down); states.addState(new int[]{},up); v.setStateListAnimator(states);
    }
    static int dp(Context c, float n) { return Math.round(n * c.getResources().getDisplayMetrics().density); }
    static GradientDrawable shape(int color, float radius, int stroke, Context c) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(c, radius));
        if (stroke != 0) d.setStroke(dp(c, 1), stroke);
        return d;
    }
    static void ripple(View v, int color, int radius) {
        GradientDrawable background = shape(color, radius, 0, v.getContext());
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(Color.argb(26, 40, 80, 45)), background, shape(WHITE, radius, 0, v.getContext())));
        press(v);
    }
    static TextView text(Context c, String text, int size, int color, boolean medium) {
        TextView v = new TextView(c); v.setText(text); v.setTextSize(size); v.setTextColor(color);
        v.setTypeface(Typeface.create(medium ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        v.setIncludeFontPadding(false); v.setLineSpacing(dp(c,2),1); return v;
    }
    static void decorate(TextView view,String kind,int color) {
        final Icon icon=new Icon(view.getContext(),kind,color); final int size=dp(view.getContext(),20);
        android.graphics.drawable.Drawable drawable=new android.graphics.drawable.Drawable(){ public void draw(Canvas c){android.graphics.Rect b=getBounds();c.save();c.translate(b.left,b.top);icon.layout(0,0,b.width(),b.height());icon.draw(c);c.restore();}public void setAlpha(int a){}public void setColorFilter(android.graphics.ColorFilter f){}public int getOpacity(){return android.graphics.PixelFormat.TRANSLUCENT;}public int getIntrinsicWidth(){return size;}public int getIntrinsicHeight(){return size;}};
        view.setCompoundDrawablesWithIntrinsicBounds(drawable,null,null,null);view.setCompoundDrawablePadding(dp(view.getContext(),8));
    }

    /** Consistent, scrollable one-hand sheet. No dependency or special permission required. */
    static final class Sheet extends Dialog {
        final Activity activity; final LinearLayout content; final ScrollView scroll;
        private float startY;
        Sheet(Activity a,String title,String subtitle,String icon) {
            super(a); activity=a; requestWindowFeature(Window.FEATURE_NO_TITLE);
            LinearLayout shell=new LinearLayout(a); shell.setOrientation(LinearLayout.VERTICAL); shell.setPadding(dp(a,22),dp(a,12),dp(a,22),dp(a,18)); shell.setBackground(shape(WHITE,28,0,a));
            LinearLayout grip=new LinearLayout(a); grip.setGravity(Gravity.CENTER); View handle=new View(a); handle.setBackground(shape(0xffccd7c7,3,0,a)); grip.addView(handle,new LinearLayout.LayoutParams(dp(a,38),dp(a,4))); shell.addView(grip,new LinearLayout.LayoutParams(-1,dp(a,24)));
            grip.setContentDescription("向下滑动关闭面板"); grip.setOnTouchListener((v,e)->{ if (e.getAction()==MotionEvent.ACTION_DOWN) startY=e.getRawY(); if (e.getAction()==MotionEvent.ACTION_UP&&e.getRawY()-startY>dp(a,55)) cancel(); return true; });
            scroll=new ScrollView(a); scroll.setVerticalScrollBarEnabled(false); scroll.setFillViewport(false); content=new LinearLayout(a); content.setOrientation(LinearLayout.VERTICAL); scroll.addView(content);
            LinearLayout heading=new LinearLayout(a); heading.setGravity(Gravity.CENTER_VERTICAL);
            Icon glyph=new Icon(a,icon,GREEN); heading.addView(glyph,new LinearLayout.LayoutParams(dp(a,38),dp(a,38)));
            TextView name=text(a,title,21,INK,true); name.setMaxLines(3); name.setEllipsize(android.text.TextUtils.TruncateAt.END); LinearLayout.LayoutParams np=new LinearLayout.LayoutParams(0,-2,1); np.leftMargin=dp(a,13); heading.addView(name,np);
            TextView close=text(a,"关闭",13,MUTED,true); close.setGravity(Gravity.CENTER); ripple(close,SOFT,14); close.setContentDescription("关闭面板"); close.setOnClickListener(v->dismiss()); heading.addView(close,new LinearLayout.LayoutParams(dp(a,48),dp(a,48))); content.addView(heading);
            if (subtitle!=null&&!subtitle.isEmpty()) { TextView sub=text(a,subtitle,13,MUTED,false); sub.setPadding(0,dp(a,14),0,dp(a,18)); sub.setTextIsSelectable(true); content.addView(sub); }
            shell.addView(scroll,new LinearLayout.LayoutParams(-1,-2)); setContentView(shell); setCanceledOnTouchOutside(true);
            setOnShowListener(d->{ Window w=getWindow(); if (w==null) return; w.setBackgroundDrawableResource(android.R.color.transparent); w.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND); WindowManager.LayoutParams p=w.getAttributes(); p.width=a.getResources().getDisplayMetrics().widthPixels-dp(a,20); p.height=-2; p.gravity=Gravity.BOTTOM; p.dimAmount=.34f; p.windowAnimations=motion()?R.style.SheetMotion:0; w.setAttributes(p);
                int max=(int)(a.getResources().getDisplayMetrics().heightPixels*.78f)-dp(a,55); content.measure(View.MeasureSpec.makeMeasureSpec(p.width-dp(a,44),View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED)); if (content.getMeasuredHeight()>max) scroll.setLayoutParams(new LinearLayout.LayoutParams(-1,max));
            });
        }
        Sheet action(String icon,String title,String subtitle,Runnable run) { return action(icon,title,subtitle,false,run); }
        Sheet action(String icon,String title,String subtitle,boolean primary,Runnable run) {
            LinearLayout row=new LinearLayout(activity); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(dp(activity,15),dp(activity,12),dp(activity,15),dp(activity,12)); row.setMinimumHeight(dp(activity,60)); ripple(row,primary?GREEN:SOFT,18);
            Icon glyph=new Icon(activity,primary&&icon.equals("mini")?"play":icon,primary?LIME:(icon.equals("trash")?DANGER:GREEN)); row.addView(glyph,new LinearLayout.LayoutParams(dp(activity,24),dp(activity,24))); LinearLayout words=new LinearLayout(activity); words.setOrientation(LinearLayout.VERTICAL); LinearLayout.LayoutParams wp=new LinearLayout.LayoutParams(0,-2,1); wp.leftMargin=dp(activity,13); row.addView(words,wp);
            words.addView(text(activity,title,15,primary?WHITE:(icon.equals("trash")?DANGER:INK),true)); if (subtitle!=null&&!subtitle.isEmpty()) { TextView sub=text(activity,subtitle,12,primary?0xffc5dbc6:MUTED,false); sub.setPadding(0,dp(activity,4),0,0); words.addView(sub); }
            Icon chevron=new Icon(activity,"arrow",primary?LIME:MUTED); row.addView(chevron,new LinearLayout.LayoutParams(dp(activity,18),dp(activity,18))); row.setFocusable(true); row.setContentDescription(title+(subtitle==null?"":"，"+subtitle)); row.setOnClickListener(v->{ dismiss(); if (run!=null) run.run(); }); LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2); rp.topMargin=dp(activity,9); content.addView(row,rp); return this;
        }
        Sheet custom(View v) { content.addView(v); return this; }
    }
    static Sheet sheet(Activity a,String title,String message,String icon) { return new Sheet(a,title,message,icon); }
    static void confirm(Activity a,String title,String message,String positive,Runnable run) { sheet(a,title,message,"trash").action("trash",positive,"删除后无法恢复",false,run).action("close","保留","",()->{}).show(); }
    static void notice(Activity a,String title,String message) { sheet(a,title,message,"info").action("check","知道了","",true,()->{}).show(); }
    static void styleDialog(AlertDialog dialog) {
        Window w=dialog.getWindow(); if (w==null) return; Context c=dialog.getContext(); w.setBackgroundDrawable(shape(WHITE,28,0,c)); w.setGravity(Gravity.BOTTOM); w.setLayout(c.getResources().getDisplayMetrics().widthPixels-dp(c,20),-2); w.setWindowAnimations(motion()?R.style.SheetMotion:0); WindowManager.LayoutParams p=w.getAttributes(); p.dimAmount=.34f; w.setAttributes(p);
        if (dialog.getButton(AlertDialog.BUTTON_POSITIVE)!=null) dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(GREEN); if (dialog.getButton(AlertDialog.BUTTON_NEGATIVE)!=null) dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(MUTED);
    }

    static final class Icon extends View {
        final String kind;
        int color;
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        Icon(Context c, String kind, int color) { super(c); this.kind = kind; this.color = color; }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            canvas.save(); canvas.scale(getWidth()/24f, getHeight()/24f);
            p.setColor(color); p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1.7f); p.setStrokeCap(Paint.Cap.ROUND); p.setStrokeJoin(Paint.Join.ROUND);
            if (kind.equals("play")) { Path path=new Path();path.moveTo(7,4);path.lineTo(20,12);path.lineTo(7,20);path.close();canvas.drawPath(path,p);
            } else if (kind.equals("audio")) {
                canvas.drawLine(9,5,9,17,p); canvas.drawLine(9,5,19,3,p); canvas.drawLine(19,3,19,15,p); canvas.drawOval(new RectF(3,15,9,20),p); canvas.drawOval(new RectF(13,13,19,18),p);
            } else if (kind.equals("share")) { canvas.drawCircle(5,12,2.5f,p); canvas.drawCircle(18,5,2.5f,p); canvas.drawCircle(18,19,2.5f,p); canvas.drawLine(7,11,15,6,p); canvas.drawLine(7,13,15,18,p);
            } else if (kind.equals("trash")) { canvas.drawLine(4,6,20,6,p); canvas.drawLine(9,3,15,3,p); Path bin=new Path(); bin.moveTo(6,6); bin.lineTo(7,21); bin.lineTo(17,21); bin.lineTo(18,6); canvas.drawPath(bin,p); canvas.drawLine(10,10,10,17,p); canvas.drawLine(14,10,14,17,p);
            } else if (kind.equals("check")) { canvas.drawCircle(12,12,9,p); Path path=new Path(); path.moveTo(7,12); path.lineTo(11,16); path.lineTo(17,8); canvas.drawPath(path,p);
            } else if (kind.equals("info")) { canvas.drawCircle(12,12,9,p); canvas.drawLine(12,11,12,17,p); canvas.drawCircle(12,7,.6f,p);
            } else if (kind.equals("search")) { canvas.drawCircle(10,10,6,p); canvas.drawLine(15,15,21,21,p);
            } else if (kind.equals("logo")) { p.setStyle(Paint.Style.FILL); canvas.drawRoundRect(new RectF(1,1,23,23),7,7,p); p.setColor(LIME); Path mark=new Path(); mark.moveTo(7,5); mark.lineTo(17,5); mark.lineTo(17,19); mark.lineTo(12,16); mark.lineTo(7,19); mark.close(); canvas.drawPath(mark,p);
            } else if (kind.equals("download")) {
                canvas.drawLine(12,3,12,14,p); Path arrow = new Path(); arrow.moveTo(7,10); arrow.lineTo(12,15); arrow.lineTo(17,10); canvas.drawPath(arrow,p);
                Path tray = new Path(); tray.moveTo(4,15); tray.lineTo(4,20); tray.lineTo(20,20); tray.lineTo(20,15); canvas.drawPath(tray,p);
            } else if (kind.equals("library")) {
                canvas.drawRoundRect(new RectF(3,3,10,10),1.5f,1.5f,p); canvas.drawRoundRect(new RectF(14,3,21,10),1.5f,1.5f,p);
                canvas.drawRoundRect(new RectF(3,14,10,21),1.5f,1.5f,p); canvas.drawRoundRect(new RectF(14,14,21,21),1.5f,1.5f,p);
            } else if (kind.equals("paste")) {
                canvas.drawRoundRect(new RectF(6,5,20,21),2,2,p); canvas.drawRoundRect(new RectF(3,2,16,18),2,2,p);
            } else if (kind.equals("arrow")) {
                canvas.drawLine(4,12,20,12,p); canvas.drawLine(15,7,20,12,p); canvas.drawLine(15,17,20,12,p);
            } else if (kind.equals("close")) {
                canvas.drawLine(6,6,18,18,p); canvas.drawLine(6,18,18,6,p);
            } else if (kind.equals("web")) {
                canvas.drawCircle(12,12,9,p); canvas.drawOval(new RectF(8,3,16,21),p); canvas.drawLine(3,12,21,12,p);
            } else if (kind.equals("image")) {
                p.setStyle(Paint.Style.FILL); canvas.drawRoundRect(new RectF(1,1,23,23),6,6,p);
                p.setColor(WHITE); p.setStyle(Paint.Style.STROKE); canvas.drawRoundRect(new RectF(5,5,19,19),2,2,p);
                canvas.drawCircle(9,9,1,p); Path mountain=new Path(); mountain.moveTo(5,17); mountain.lineTo(10,12); mountain.lineTo(13,15); mountain.lineTo(16,11); mountain.lineTo(19,15); canvas.drawPath(mountain,p);
            } else {
                p.setStyle(Paint.Style.FILL); canvas.drawRoundRect(new RectF(1,1,23,23),6,6,p);
                p.setColor(kind.equals("mini") ? WHITE : LIME); Path path = new Path(); path.moveTo(9,7); path.lineTo(9,17); path.lineTo(17,12); path.close(); canvas.drawPath(path,p);
            }
            canvas.restore();
        }
    }

    static final class Artwork extends View {
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        Artwork(Context c) { super(c); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO); }
        @Override protected void onDraw(Canvas c) {
            c.save(); c.scale(getWidth()/120f, getHeight()/140f);
            p.setColor(Color.rgb(226,239,211)); c.drawCircle(64,70,55,p);
            c.save(); c.rotate(-13,64,67); p.setColor(Color.rgb(190,213,150)); c.drawRoundRect(new RectF(28,28,104,122),15,15,p); c.restore();
            c.save(); c.rotate(8,61,71); p.setColor(GREEN); c.drawRoundRect(new RectF(19,18,94,112),14,14,p);
            p.setColor(LIME); c.drawRoundRect(new RectF(26,26,87,96),9,9,p);
            p.setColor(GREEN); Path path = new Path(); path.moveTo(48,43); path.lineTo(48,76); path.lineTo(72,59); path.close(); c.drawPath(path,p);
            p.setColor(Color.rgb(150,183,116)); c.drawCircle(54,104,2,p); c.drawCircle(61,104,2,p); c.drawCircle(68,104,2,p); c.restore();
            p.setColor(Color.rgb(166,194,123)); c.drawCircle(105,22,4,p); c.drawCircle(11,116,3,p);
            p.setStrokeWidth(2); c.drawLine(96,119,107,119,p); c.drawLine(101.5f,113.5f,101.5f,124.5f,p); c.restore();
        }
    }
}
