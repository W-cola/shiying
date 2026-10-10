package cn.shiying.mobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.app.Instrumentation;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import cn.shiying.mobile.core.ChannelsCodec;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;

/** Controlled client-format sample; does not claim a live WeChat share was tested. */
public final class NativeChannelsChecks extends Instrumentation {
    void check(boolean value,String message) { if (!value) throw new AssertionError(message); }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    byte[] digest(Context context,Uri uri) throws Exception {
        MessageDigest hash=MessageDigest.getInstance("SHA-256");
        try (InputStream input=context.getContentResolver().openInputStream(uri)) { byte[] buffer=new byte[8192]; int n; while ((n=input.read(buffer))>0) hash.update(buffer,0,n); }
        return hash.digest();
    }
    @Override public void onStart() {
        Bundle report=new Bundle();
        try {
            Context context=getTargetContext(); startActivitySync(new Intent().setClassName(context,"cn.shiying.mobile.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            Uri original=null; JSONArray records=RecordStore.read(context);
            for (int i=0;i<records.length();i++) { JSONObject row=records.optJSONObject(i); if (row!=null&&row.optBoolean("compound")&&row.optString("noteId").equals("BV1GJ411x7h7")&&!row.optString("localUri").isEmpty()) { original=Uri.parse(row.optString("localUri")); break; } }
            check(original!=null,"A real already tested MP4 is available as the controlled sample");
            String name="channels-codec-sample-"+System.currentTimeMillis()+".bin"; ContentValues values=new ContentValues(); values.put(MediaStore.Downloads.DISPLAY_NAME,name); values.put(MediaStore.Downloads.MIME_TYPE,"application/octet-stream"); values.put(MediaStore.Downloads.RELATIVE_PATH,"Download/拾影");
            Uri encoded=context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values); String key="123456789"; ChannelsCodec codec=new ChannelsCodec(key); long bytes=0;
            try (InputStream input=context.getContentResolver().openInputStream(original);OutputStream output=context.getContentResolver().openOutputStream(encoded)) {
                byte[] buffer=new byte[8192]; int n; while ((n=input.read(buffer))>0) { codec.apply(buffer,0,n); output.write(buffer,0,n); bytes+=n; }
            }
            String path; try (Cursor c=context.getContentResolver().query(encoded,new String[]{"_data"},null,null,null)) { check(c!=null&&c.moveToFirst(),"Encoded sample has a local path"); path=c.getString(0); }
            DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE); long child=manager.addCompletedDownload("视频号格式测试样本","Controlled local sample",false,"application/octet-stream",path,bytes,true);
            long id=4000000000000000L+System.currentTimeMillis(); android.content.SharedPreferences prefs=context.getSharedPreferences("compound",0); int serial=prefs.getInt("serial",100000)+1; prefs.edit().putInt("serial",serial).commit();
            JSONObject job=new JSONObject().put("id",id).put("schedulerId",serial).put("mode","channels").put("decodeKey",key).put("state","downloading").put("expected",1).put("title","视频号格式验证（受控样本）").put("file","视频号格式验证（受控样本） "+id+".mp4")
                .put("parts",new JSONArray().put(new JSONObject().put("id",child).put("kind","video")));
            CompoundDownloads.put(context,id,job);
            JSONObject record=new JSONObject().put("id",id).put("title","视频号格式验证（受控样本）").put("file",job.getString("file")).put("mime","video/mp4").put("compound",true).put("directory","Movies"); records.put(record); RecordStore.save(context,records);
            CompoundDownloads.query(context,record,new long[3]); long deadline=System.currentTimeMillis()+45000;
            while (System.currentTimeMillis()<deadline&&!CompoundDownloads.job(context,id).optString("state").equals("done")) {
                if (CompoundDownloads.job(context,id).optString("state").equals("failed")) throw new AssertionError("Client-format conversion failed"); Thread.sleep(100);
            }
            check(CompoundDownloads.job(context,id).optString("state").equals("done"),"Normal playback data converted to an MP4");
            check(!CompoundDownloads.job(context,id).has("decodeKey"),"Playback parameter cleared after successful conversion");
            Uri clear=Uri.parse(CompoundDownloads.job(context,id).getString("localUri"));
            check(java.util.Arrays.equals(digest(context,original),digest(context,clear)),"Converted MP4 is byte-identical to the original audio/video file");
            try (Cursor c=context.getContentResolver().query(clear,new String[]{"relative_path","is_pending"},null,null,null)) { check(c!=null&&c.moveToFirst()&&c.getString(0).equals("Movies/拾影/")&&c.getInt(1)==0,"Converted sample published to gallery"); }
            report.putString("result","PASS: known client-format sample converted on Android, original MP4 SHA-256 restored exactly, published to gallery");
            report.putString("fixture","controlled local sample using an already tested MP4; not a live WeChat share link"); report.putLong("bytes",bytes); finish(Activity.RESULT_OK,report);
        } catch (Throwable e) { report.putString("error",e.toString()); finish(Activity.RESULT_CANCELED,report); }
    }
}
