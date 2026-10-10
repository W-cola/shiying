package cn.shiying.mobile;

import android.app.DownloadManager;
import android.content.Context;
import android.database.Cursor;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Environment;
import cn.shiying.mobile.core.MediaHeaders;
import java.io.File;
import java.io.InputStream;
import java.util.Set;
import java.util.Collections;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

/** Publish only completed, header-verified downloads to Android's media library. */
final class MediaPublisher {
    private static final ExecutorService worker=Executors.newSingleThreadExecutor();
    private static final Set<Long> pending=Collections.newSetFromMap(new ConcurrentHashMap<Long,Boolean>());
    static void publish(Context context,long id,Runnable finished) {
        Context app=context.getApplicationContext();
        if (app.getSharedPreferences("gallery",0).getBoolean("deleted_"+id,false)) { finished.run(); return; }
        if (id<0||!pending.add(id)) { finished.run(); return; }
        Runnable done=()-> { pending.remove(id); finished.run(); };
        worker.execute(()-> {
            try {
                if (!app.getSharedPreferences("gallery",0).getString("uri_"+id,"").isEmpty()) { done.run(); return; }
                DownloadManager manager=(DownloadManager)app.getSystemService(Context.DOWNLOAD_SERVICE);
                String local,mime;
                try (Cursor cursor=manager.query(new DownloadManager.Query().setFilterById(id))) {
                    if (cursor==null||!cursor.moveToFirst()||cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))!=DownloadManager.STATUS_SUCCESSFUL) { done.run(); return; }
                    local=cursor.getString(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_LOCAL_URI));
                    mime=cursor.getString(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_MEDIA_TYPE));
                }
                if (local==null||mime==null||(!mime.startsWith("video/")&&!mime.startsWith("image/"))) { done.run(); return; }
                Uri fileUri=Uri.parse(local); if (!"file".equals(fileUri.getScheme())) { done.run(); return; }
                File file=new File(fileUri.getPath()).getCanonicalFile();
                String root=Environment.getExternalStorageDirectory().getCanonicalPath()+File.separator;
                if (!file.getPath().startsWith(root)||!file.isFile()) { done.run(); return; }
                Uri download=manager.getUriForDownloadedFile(id); if (download==null) { done.run(); return; }
                try (InputStream input=app.getContentResolver().openInputStream(download)) {
                    if (input==null) { done.run(); return; }
                    byte[] header=new byte[64]; int n=input.read(header);
                    if (MediaHeaders.detect(header,Math.max(0,n),mime.startsWith("image/")?"image":"video")==null) { done.run(); return; }
                }
                MediaScannerConnection.scanFile(app,new String[]{file.getPath()},new String[]{mime},(path,uri)-> {
                    try { if (uri!=null&&!app.getSharedPreferences("gallery",0).getBoolean("deleted_"+id,false)) app.getSharedPreferences("gallery",0).edit().putString("uri_"+id,uri.toString()).apply(); }
                    finally { done.run(); }
                });
            } catch (Exception e) { done.run(); }
        });
    }
    static Uri beginDelete(Context context,long id) {
        android.content.SharedPreferences prefs=context.getSharedPreferences("gallery",0);
        String uri=prefs.getString("uri_"+id,""); prefs.edit().putBoolean("deleted_"+id,true).apply();
        return uri.isEmpty()?null:Uri.parse(uri);
    }
    static void finishDelete(Context context,long id) { context.getSharedPreferences("gallery",0).edit().remove("uri_"+id).apply(); }
}
