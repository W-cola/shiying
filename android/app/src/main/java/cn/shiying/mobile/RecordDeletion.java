package cn.shiying.mobile;

import android.app.DownloadManager;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import org.json.JSONObject;
import java.io.File;

/** Delete the selected owned download and its media entry before removing its history. */
final class RecordDeletion {
    static void delete(Context context,DownloadManager manager,JSONObject record) throws Exception {
        if (AlbumRecords.isAlbum(record)) {
            org.json.JSONArray items=record.getJSONArray("items"); String error="";
            for (int i=0;i<items.length();i++) try { delete(context,manager,items.getJSONObject(i)); }
            catch (Exception e) { error=e.getMessage()==null?"部分文件未删除。":e.getMessage(); }
            if (!error.isEmpty()) throw new Exception(error+" 未删除的记录已保留，可以重试。");
            return;
        }
        long id=record.getLong("id");
        if (record.optBoolean("compound")) { CompoundDownloads.cancel(context,id); RecordStore.remove(context,id); return; }
        String exported=record.optString("localUri");
        if (!exported.isEmpty()) {
            Uri uri=Uri.parse(exported);
            if (!"content".equals(uri.getScheme())||!"media".equals(uri.getAuthority())) throw new Exception("正文保存地址无效。");
            context.getContentResolver().delete(uri,null,null);
            RecordStore.remove(context,id);
            return;
        }
        File file=null;
        try (Cursor cursor=manager.query(new DownloadManager.Query().setFilterById(id))) {
            if (cursor!=null&&cursor.moveToFirst()) {
                String local=cursor.getString(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_LOCAL_URI));
                if (local!=null) { Uri uri=Uri.parse(local); if ("file".equals(uri.getScheme())) file=new File(uri.getPath()); }
            }
        }
        if (file==null) {
            String directory=record.optString("directory",Environment.DIRECTORY_DOWNLOADS);
            String name=record.optString("file");
            if ((!Environment.DIRECTORY_DOWNLOADS.equals(directory)&&!Environment.DIRECTORY_MOVIES.equals(directory)&&!Environment.DIRECTORY_PICTURES.equals(directory))||name.isEmpty()||name.contains("/")||name.contains("\\")) throw new Exception("文件地址无效，无法确认要删除的文件。");
            file=new File(new File(Environment.getExternalStoragePublicDirectory(directory),"拾影"),name);
        }
        file=file.getCanonicalFile();
        String root=Environment.getExternalStorageDirectory().getCanonicalPath()+File.separator;
        if (!file.getPath().startsWith(root)) throw new Exception("文件不在本应用的保存目录中。");
        Uri gallery=MediaPublisher.beginDelete(context,id);
        int removed=manager.remove(id); // Android also removes the linked file and MediaStore row.
        if (file.isFile()&&!file.delete()) throw new Exception("手机未允许删除这个文件，请检查文件是否被其他应用占用后重试。");
        if (file.isFile()) throw new Exception("文件仍存在，删除未完成。");
        // A second delete of an already removed MediaStore URI can fail scoped-storage permission checks.
        if (gallery!=null&&removed==0) {
            try { context.getContentResolver().delete(gallery,null,null); }
            catch (SecurityException e) {
                android.media.MediaScannerConnection.scanFile(context.getApplicationContext(),new String[]{file.getPath()},new String[]{record.optString("mime","video/mp4")},null);
            }
        }
        MediaPublisher.finishDelete(context,id);
        RecordStore.remove(context,id);
    }
}
