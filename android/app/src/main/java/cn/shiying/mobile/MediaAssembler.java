package cn.shiying.mobile;

import android.app.DownloadManager;
import android.content.ContentValues;
import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/** Re-mux normal AVC/AAC MP4 tracks with Android APIs; no decoding, DRM or external service. */
final class MediaAssembler {
    private static final class Input {
        final MediaExtractor extractor=new MediaExtractor(); final String kind; int track=-1;
        Input(Context context,Uri uri,String kind) throws Exception { this.kind=kind; extractor.setDataSource(context,uri,null); }
        int find(String type) { for (int i=0;i<extractor.getTrackCount();i++) if (extractor.getTrackFormat(i).getString(MediaFormat.KEY_MIME).startsWith(type+"/")) return i; return -1; }
        void close() { extractor.release(); }
    }
    static void assemble(Context context,long id) throws Exception {
        JSONObject job=CompoundDownloads.job(context,id); DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);
        JSONArray parts=job.getJSONArray("parts"); List<Uri> sources=new ArrayList<>(); List<String> kinds=new ArrayList<>();
        if(!job.optString("localSource").isEmpty()){sources.add(Uri.parse(job.getString("localSource")));kinds.add("video");}
        for (int i=0;i<parts.length();i++) { JSONObject part=parts.getJSONObject(i); Uri uri=manager.getUriForDownloadedFile(part.getLong("id")); if (uri==null) throw new Exception("合并所需的媒体片段已移除。"); sources.add(uri); kinds.add(part.optString("kind","video")); }
        boolean audio=job.optBoolean("audio"); File cache=new File(context.getCacheDir(),"assembled_"+id+(audio?".m4a":".mp4")); File decoded=new File(context.getCacheDir(),"decoded_"+id+".mp4"); CompoundDownloads.update(context,id,"cache",cache.getPath());
        try {
            if (job.optString("mode").equals("channels")) {
                if (sources.size()!=1) throw new Exception("不完整的网页视频播放数据。");
                cn.shiying.mobile.core.ChannelsCodec codec=new cn.shiying.mobile.core.ChannelsCodec(job.getString("decodeKey"));
                File clear=audio?decoded:cache;
                try (java.io.InputStream input=context.getContentResolver().openInputStream(sources.get(0));OutputStream output=new java.io.FileOutputStream(clear)) {
                    if (input==null) throw new Exception("媒体无法读取。"); byte[] buffer=new byte[8192]; int n;
                    while ((n=input.read(buffer))>0) { if (CompoundDownloads.cancelled(context,id)||Thread.currentThread().isInterrupted()) throw new InterruptedException(); codec.apply(buffer,0,n); output.write(buffer,0,n); }
                }
                MediaExtractor verifier=new MediaExtractor(); try {
                    verifier.setDataSource(clear.getPath()); boolean video=false; for (int i=0;i<verifier.getTrackCount();i++) if (verifier.getTrackFormat(i).getString(MediaFormat.KEY_MIME).startsWith("video/")) video=true;
                    if (!video) throw new Exception("网页媒体没有正常的视频轨道。");
                } finally { verifier.release(); }
                if (audio) AudioExtractor.extract(context,id,java.util.Collections.singletonList(Uri.fromFile(decoded)),cache);
            } else if (audio) AudioExtractor.extract(context,id,sources,cache);
            else mux(context,id,sources,kinds,job.optString("mode"),cache);
            if (CompoundDownloads.cancelled(context,id)||Thread.currentThread().isInterrupted()) throw new InterruptedException();
            publish(context,id,job,cache);
        } finally { cache.delete(); decoded.delete(); }
    }
    static void mux(Context context,long id,List<Uri> sources,List<String> kinds,String mode,File output) throws Exception {
        List<Input> inputs=new ArrayList<>(); MediaMuxer muxer=null; boolean started=false;
        try {
            for (int i=0;i<sources.size();i++) inputs.add(new Input(context,sources.get(i),kinds.get(i)));
            if (inputs.isEmpty()) throw new Exception("媒体片段为空。");
            muxer=new MediaMuxer(output.getPath(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            if ("dash".equals(mode)) {
                for (Input input:inputs) { input.track=input.find(input.kind); if (input.track<0) throw new Exception("媒体缺少预期的"+("audio".equals(input.kind)?"音频":"视频")+"轨道。"); }
                boolean video=false,audio=false; int[] tracks=new int[inputs.size()];
                for (int i=0;i<inputs.size();i++) { Input input=inputs.get(i); tracks[i]=muxer.addTrack(input.extractor.getTrackFormat(input.track)); video|=input.kind.equals("video"); audio|=input.kind.equals("audio"); }
                if (!video||!audio) throw new Exception("分离的视频必须同时包含画面和声音。");
                muxer.start(); started=true;
                for (int i=0;i<inputs.size();i++) copy(context,id,inputs.get(i),inputs.get(i).track,muxer,tracks[i],0);
            } else if ("concat".equals(mode)) {
                Input first=inputs.get(0); int video=first.find("video"),audio=first.find("audio");
                if (video<0) throw new Exception("片段中没有视频轨道。"); MediaFormat picture=first.extractor.getTrackFormat(video),sound=audio<0?null:first.extractor.getTrackFormat(audio);
                int videoOut=muxer.addTrack(picture),audioOut=sound==null?-1:muxer.addTrack(sound); muxer.start(); started=true; long offset=0;
                for (Input input:inputs) {
                    int v=input.find("video"),a=input.find("audio");
                    if (v<0||!sameFormat(picture,input.extractor.getTrackFormat(v))||(sound!=null&&(a<0||!sameFormat(sound,input.extractor.getTrackFormat(a))))) throw new Exception("分段编码不一致，无法无损合并；可改选完整 MP4。");
                    long length=copy(context,id,input,v,muxer,videoOut,offset);
                    if (a>=0&&audioOut>=0) length=Math.max(length,copy(context,id,input,a,muxer,audioOut,offset));
                    offset=length+40000;
                }
            } else throw new Exception("不支持的媒体合并方式。");
            muxer.stop(); started=false;
        } finally {
            for (Input input:inputs) input.close();
            if (muxer!=null) { if (started) try { muxer.stop(); } catch (Exception ignored) { } muxer.release(); }
        }
    }
    private static boolean sameFormat(MediaFormat a,MediaFormat b) {
        if (!a.getString(MediaFormat.KEY_MIME).equals(b.getString(MediaFormat.KEY_MIME))) return false;
        for (String key:new String[]{MediaFormat.KEY_WIDTH,MediaFormat.KEY_HEIGHT,MediaFormat.KEY_SAMPLE_RATE,MediaFormat.KEY_CHANNEL_COUNT}) if (a.containsKey(key)&&(!b.containsKey(key)||a.getInteger(key)!=b.getInteger(key))) return false;
        for (String key:new String[]{"csd-0","csd-1"}) if (a.containsKey(key)&&(!b.containsKey(key)||!a.getByteBuffer(key).duplicate().equals(b.getByteBuffer(key).duplicate()))) return false;
        return true;
    }
    private static long copy(Context context,long id,Input source,int track,MediaMuxer output,int outTrack,long offset) throws Exception {
        source.extractor.selectTrack(track); source.extractor.seekTo(0,MediaExtractor.SEEK_TO_CLOSEST_SYNC);
        ByteBuffer buffer=ByteBuffer.allocate(8*1024*1024); MediaCodec.BufferInfo info=new MediaCodec.BufferInfo(); long first=-1,last=offset; int frames=0;
        try {
            while (true) {
                if (Thread.currentThread().isInterrupted()||CompoundDownloads.cancelled(context,id)) throw new InterruptedException();
                buffer.clear(); int n=source.extractor.readSampleData(buffer,0); if (n<0) break;
                if ((source.extractor.getSampleFlags()&MediaExtractor.SAMPLE_FLAG_ENCRYPTED)!=0) throw new Exception("受保护的媒体不能合并。");
                long time=source.extractor.getSampleTime(); if (first<0) first=time;
                info.set(0,n,Math.max(0,time-first)+offset,source.extractor.getSampleFlags()&MediaExtractor.SAMPLE_FLAG_SYNC);
                output.writeSampleData(outTrack,buffer,info); last=Math.max(last,info.presentationTimeUs); frames++; if (!source.extractor.advance()) break;
            }
        } finally { source.extractor.unselectTrack(track); }
        if (frames==0) throw new Exception("媒体轨道没有可保存的内容。"); return last;
    }
    private static void publish(Context context,long id,JSONObject job,File file) throws Exception {
        boolean audio=job.optBoolean("audio"); String mime=audio?"audio/mp4":"video/mp4",directory=audio?Environment.DIRECTORY_MUSIC:Environment.DIRECTORY_MOVIES;
        Uri uri=null; File legacy=null; long systemId=-1;
        try {
            if (Build.VERSION.SDK_INT>=29) {
                ContentValues values=new ContentValues(); values.put(MediaStore.MediaColumns.DISPLAY_NAME,job.getString("file")); values.put(MediaStore.MediaColumns.MIME_TYPE,mime); values.put(MediaStore.MediaColumns.RELATIVE_PATH,directory+"/拾影"); values.put(MediaStore.MediaColumns.IS_PENDING,1);
                if (audio) { values.put(MediaStore.Audio.Media.TITLE,job.optString("title")); values.put(MediaStore.Audio.Media.IS_MUSIC,1); }
                uri=context.getContentResolver().insert(audio?MediaStore.Audio.Media.EXTERNAL_CONTENT_URI:MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values); if (uri==null) throw new Exception("媒体文件无法创建。");
                CompoundDownloads.update(context,id,"outputUri",uri.toString());
                try (FileInputStream input=new FileInputStream(file);OutputStream output=context.getContentResolver().openOutputStream(uri)) { if (output==null) throw new Exception("相册视频无法写入。"); transfer(context,id,input,output); }
                if (CompoundDownloads.cancelled(context,id)||Thread.currentThread().isInterrupted()) throw new InterruptedException();
                ContentValues ready=new ContentValues(); ready.put(MediaStore.Video.Media.IS_PENDING,0); context.getContentResolver().update(uri,ready,null,null);
            } else {
                File folder=new File(Environment.getExternalStoragePublicDirectory(directory),"拾影"); if (!folder.exists()&&!folder.mkdirs()) throw new Exception("媒体保存目录无法创建。");
                legacy=new File(folder,job.getString("file"));
                CompoundDownloads.update(context,id,"legacyPath",legacy.getPath());
                try (FileInputStream input=new FileInputStream(file);OutputStream output=new java.io.FileOutputStream(legacy)) { transfer(context,id,input,output); }
                DownloadManager manager=(DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE); systemId=manager.addCompletedDownload(job.optString("title"),"拾影 · 已保存",true,mime,legacy.getPath(),file.length(),true); uri=manager.getUriForDownloadedFile(systemId);
                CompoundDownloads.update(context,id,"systemId",systemId); android.media.MediaScannerConnection.scanFile(context,new String[]{legacy.getPath()},new String[]{mime},null);
            }
            if (uri==null||!CompoundDownloads.complete(context,id,uri.toString(),file.length())) throw new InterruptedException();
            CompoundDownloads.cleanupParts(context,job);
        } catch (Exception e) {
            if (uri!=null) try { context.getContentResolver().delete(uri,null,null); } catch (Exception ignored) { }
            if (systemId>=0) ((DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE)).remove(systemId);
            if (legacy!=null) legacy.delete(); throw e;
        }
    }
    private static void transfer(Context context,long id,java.io.InputStream input,OutputStream output) throws Exception {
        byte[] buffer=new byte[8192]; int n; while ((n=input.read(buffer))>0) { if (CompoundDownloads.cancelled(context,id)||Thread.currentThread().isInterrupted()) throw new InterruptedException(); output.write(buffer,0,n); }
    }
}
