package cn.shiying.mobile;

import android.app.DownloadManager;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.PersistableBundle;
import android.webkit.CookieManager;
import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.List;
import java.util.Locale;

/** System-managed part downloads plus a persistent native assembly job. */
final class CompoundDownloads {
    private static SharedPreferences prefs(Context context) { return context.getSharedPreferences("compound",0); }
    private static long newId(Context context) { long id=4000000000000000L+System.currentTimeMillis(); while(prefs(context).contains("job_"+id))id++;return id; }
    static synchronized JSONObject enqueueLocalAudio(Context context,JSONObject original,Uri source) throws Exception {
        if(!"content".equals(source.getScheme()))throw new Exception("视频地址无效。");
        long id=newId(context); int serial=prefs(context).getInt("serial",100000)+1;prefs(context).edit().putInt("serial",serial).commit();
        String name=VideoResolver.filename(original.optString("title"),original.optString("noteId"))+" "+new java.text.SimpleDateFormat("yyyyMMdd_HHmmss_SSS",Locale.ROOT).format(new java.util.Date())+"_原声.m4a";
        JSONObject job=new JSONObject().put("id",id).put("schedulerId",serial).put("mode","direct").put("audio",true).put("localSource",source.toString()).put("title",original.optString("title")).put("file",name).put("state","downloading").put("parts",new JSONArray());put(context,id,job);
        JSONObject record=new JSONObject(original.toString());record.remove("appError");record.remove("checking");record.remove("deleting");return record.put("id",id).put("title",original.optString("title")+" · 原声").put("file",name).put("mime","audio/mp4").put("directory","Music").put("time",System.currentTimeMillis()).put("compound",true).put("localUri","").put("verified",false).put("bytes",0);
    }
    static synchronized JSONObject job(Context context,long id) {
        try { return new JSONObject(prefs(context).getString("job_"+id,"{}")); } catch (Exception e) { return new JSONObject(); }
    }
    static synchronized void put(Context context,long id,JSONObject value) { prefs(context).edit().putString("job_"+id,value.toString()).commit(); }
    static synchronized void update(Context context,long id,String key,Object value) {
        JSONObject job=job(context,id);
        if (job.optString("state").equals("done")&&(key.equals("error")||key.equals("state")&&!"cancelled".equals(value))) return;
        if (job.optString("state").equals("cancelled")&&key.equals("state")&&!"cancelled".equals(value)) return;
        try { job.put(key,value); put(context,id,job); } catch (Exception ignored) { }
    }
    static JSONArray enqueue(Context context,DownloadManager downloads,VideoInfo info,List<DownloadCoordinator.Prepared> parts) throws Exception {
        return enqueue(context,downloads,info,parts,false);
    }
    static JSONArray enqueueAudio(Context context,DownloadManager downloads,VideoInfo info,List<DownloadCoordinator.Prepared> parts) throws Exception {
        return enqueue(context,downloads,info,parts,true);
    }
    private static synchronized JSONArray enqueue(Context context,DownloadManager downloads,VideoInfo info,List<DownloadCoordinator.Prepared> parts,boolean audio) throws Exception {
        if (parts.isEmpty()) throw new Exception("没有可用的媒体来源。");
        long id=newId(context);
        int serial=prefs(context).getInt("serial",100000)+1; prefs(context).edit().putInt("serial",serial).commit();
        String name=VideoResolver.filename(info.title,info.id)+" "+new java.text.SimpleDateFormat("yyyyMMdd_HHmmss_SSS",Locale.ROOT).format(new java.util.Date())+(audio?"_原声.m4a":".mp4");
        JSONObject job=new JSONObject().put("id",id).put("schedulerId",serial).put("mode",parts.get(0).mode).put("title",info.title).put("file",name).put("state","downloading").put("expected",parts.size()).put("parts",new JSONArray());
        job.put("audio",audio);
        if (parts.get(0).mode.equals("channels")) job.put("decodeKey",parts.get(0).asset.decodeKey);
        put(context,id,job); JSONArray ids=job.getJSONArray("parts");
        try {
            for (int i=0;i<parts.size();i++) {
                DownloadCoordinator.Prepared part=parts.get(i);
                DownloadManager.Request request=new DownloadManager.Request(Uri.parse(part.media.url));
                request.setTitle(info.title); request.setDescription("拾影 · 正在保存"); request.setMimeType(part.media.mime);
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE); request.setAllowedOverMetered(true); request.setAllowedOverRoaming(false);
                request.addRequestHeader("User-Agent",info.userAgent); request.addRequestHeader("Referer",VideoResolver.referer(info)); request.addRequestHeader("Accept-Encoding","identity");
                String cookie=CookieManager.getInstance().getCookie(part.media.url); if (cookie!=null&&!cookie.isEmpty()) request.addRequestHeader("Cookie",cookie);
                request.setDestinationInExternalFilesDir(context,"media-parts",id+"_"+i+"."+part.media.ext);
                long child=downloads.enqueue(request); ids.put(new JSONObject().put("id",child).put("kind",part.asset.kind)); put(context,id,job);
            }
            JSONObject record=DownloadCoordinator.record(info,id,info.title+(audio?" · 原声":""),name,audio?"audio/mp4":"video/mp4").put("compound",true).put("directory",audio?"Music":"Movies");
            return new JSONArray().put(record);
        } catch (Exception e) { cancel(context,id); throw e; }
    }
    static int query(Context context,JSONObject record,long[] stats) {
        long id=record.optLong("id"); JSONObject job=job(context,id); String state=job.optString("state");
        if ("done".equals(state)) { stats[0]=stats[1]=job.optLong("bytes"); return DownloadManager.STATUS_SUCCESSFUL; }
        if ("failed".equals(state)||"cancelled".equals(state)) { stats[2]=DownloadManager.ERROR_CANNOT_RESUME; return DownloadManager.STATUS_FAILED; }
        if(!job.optString("localSource").isEmpty()){schedule(context,id);return DownloadManager.STATUS_RUNNING;}
        JSONArray parts=job.optJSONArray("parts"); if (parts==null||parts.length()==0) return DownloadManager.STATUS_PENDING;
        DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE); boolean all=true,paused=false;
        for (int i=0;i<parts.length();i++) {
            JSONObject part=parts.optJSONObject(i); if (part==null) return DownloadManager.STATUS_FAILED;
            try (Cursor cursor=manager.query(new DownloadManager.Query().setFilterById(part.optLong("id")))) {
                if (cursor==null||!cursor.moveToFirst()) { if (job(context,id).optString("state").equals("done")) return query(context,record,stats); fail(context,id,"下载片段已移除，请重新解析。"); return DownloadManager.STATUS_FAILED; }
                int status=cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                stats[0]+=cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR)); stats[1]+=Math.max(0,cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES)));
                if (status==DownloadManager.STATUS_FAILED) { fail(context,id,"媒体下载未完成，请重新解析或检查网络。"); return status; }
                if (status!=DownloadManager.STATUS_SUCCESSFUL) all=false; if (status==DownloadManager.STATUS_PAUSED) paused=true;
            } catch (Exception e) { return DownloadManager.STATUS_PENDING; }
        }
        if (all&&parts.length()==job.optInt("expected")) schedule(context,id);
        return paused?DownloadManager.STATUS_PAUSED:DownloadManager.STATUS_RUNNING;
    }
    static synchronized void schedule(Context context,long id) {
        JSONObject job=job(context,id); String state=job.optString("state"); if (state.equals("done")||state.equals("failed")||state.equals("cancelled")) return;
        JobScheduler scheduler=(JobScheduler)context.getSystemService(Context.JOB_SCHEDULER_SERVICE); int schedulerId=job.optInt("schedulerId");
        if (scheduler.getPendingJob(schedulerId)!=null) return;
        PersistableBundle extras=new PersistableBundle(); extras.putLong("recordId",id);
        int result=scheduler.schedule(new JobInfo.Builder(schedulerId,new ComponentName(context,MediaAssemblyJob.class)).setExtras(extras).setPersisted(true).setOverrideDeadline(0).build());
        if (result==JobScheduler.RESULT_SUCCESS) update(context,id,"state","assembling");
    }
    static boolean childComplete(Context context,long child) {
        boolean found=false;
        for (String key:prefs(context).getAll().keySet()) if (key.startsWith("job_")) {
            long id; try { id=Long.parseLong(key.substring(4)); } catch (Exception e) { continue; }
            JSONObject job=job(context,id); JSONArray parts=job.optJSONArray("parts"); if (parts==null) continue;
            for (int i=0;i<parts.length();i++) if (parts.optJSONObject(i)!=null&&parts.optJSONObject(i).optLong("id")==child) {
                found=true; query(context,record(id),new long[3]); break;
            }
        } return found;
    }
    private static JSONObject record(long id) { try { return new JSONObject().put("id",id); } catch (Exception e) { return new JSONObject(); } }
    static void recover(Context context) {
        for (JSONObject record:records(context)) if (record.optBoolean("compound")) query(context,record,new long[3]);
    }
    private static java.util.List<JSONObject> records(Context context) {
        java.util.List<JSONObject> list=new java.util.ArrayList<>(); JSONArray all=RecordStore.read(context); for (int i=0;i<all.length();i++) if (all.optJSONObject(i)!=null) list.add(all.optJSONObject(i)); return list;
    }
    static JSONObject decorate(Context context,JSONObject record) {
        if (!record.optBoolean("compound")) return record;
        JSONObject job=job(context,record.optLong("id"));
        try {
            if (job.optString("state").equals("done")) record.put("localUri",job.optString("localUri")).put("bytes",job.optLong("bytes")).put("verified",true);
            if (!job.optString("error").isEmpty()) record.put("appError",job.optString("error"));
        } catch (Exception ignored) { } return record;
    }
    static synchronized boolean cancelled(Context context,long id) { return job(context,id).optString("state").equals("cancelled")||context.getSharedPreferences("gallery",0).getBoolean("removed_"+id,false); }
    static synchronized boolean complete(Context context,long id,String uri,long bytes) {
        if (cancelled(context,id)) return false; JSONObject job=job(context,id);
        try { job.put("state","done").put("localUri",uri).put("bytes",bytes); job.remove("error"); job.remove("decodeKey"); put(context,id,job); return true; }
        catch (Exception e) { return false; }
    }
    static void cancel(Context context,long id) throws Exception {
        JSONObject job=job(context,id); update(context,id,"state","cancelled"); update(context,id,"error","下载已取消");
        ((JobScheduler)context.getSystemService(Context.JOB_SCHEDULER_SERVICE)).cancel(job.optInt("schedulerId")); cleanupParts(context,job);
        long systemId=job.optLong("systemId",-1);
        if (systemId>=0) ((DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE)).remove(systemId);
        String output=job.optString("outputUri",job.optString("localUri"));
        if (!output.isEmpty()&&systemId<0) {
            try { context.getContentResolver().delete(Uri.parse(output),null,null); }
            catch (SecurityException e) { throw new Exception("手机未允许删除这个视频，请重试；下载记录已保留。",e); }
        }
        String legacy=job.optString("legacyPath");
        if (!legacy.isEmpty()) {
            java.io.File file=new java.io.File(legacy).getCanonicalFile();
            String folder=new java.io.File(android.os.Environment.getExternalStoragePublicDirectory(job.optBoolean("audio")?android.os.Environment.DIRECTORY_MUSIC:android.os.Environment.DIRECTORY_MOVIES),"拾影").getCanonicalPath()+java.io.File.separator;
            if (!file.getPath().startsWith(folder)) throw new Exception("视频保存地址无效。");
            if (file.exists()&&!file.delete()) throw new Exception("视频文件删除失败，请重试；下载记录已保留。");
        }
        String cache=job.optString("cache"); if (!cache.isEmpty()) { java.io.File file=new java.io.File(cache); if (file.getCanonicalPath().startsWith(context.getCacheDir().getCanonicalPath()+java.io.File.separator)) file.delete(); }
        synchronized (CompoundDownloads.class) { JSONObject current=job(context,id); current.remove("decodeKey"); put(context,id,current); }
    }
    private static synchronized void fail(Context context,long id,String message) {
        JSONObject current=job(context,id); String state=current.optString("state");
        if (state.equals("done")||state.equals("cancelled")||state.equals("failed")) return;
        try { current.put("state","failed").put("error",message); current.remove("decodeKey"); put(context,id,current); } catch (Exception ignored) { }
        cleanupParts(context,current);
    }
    static void cleanupParts(Context context,JSONObject job) {
        DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE); JSONArray parts=job.optJSONArray("parts"); if (parts==null) return;
        for (int i=0;i<parts.length();i++) { JSONObject part=parts.optJSONObject(i); if (part!=null) manager.remove(part.optLong("id")); }
    }
}
