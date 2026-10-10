package cn.shiying.mobile;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.net.Uri;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/** Extract AAC packets unchanged; decode other system-supported sound to AAC locally. */
final class AudioExtractor {
    private static void check(Context c,long id) throws InterruptedException { if (Thread.currentThread().isInterrupted()||CompoundDownloads.cancelled(c,id)) throw new InterruptedException(); }
    static int audio(MediaExtractor e) { for (int i=0;i<e.getTrackCount();i++) if (e.getTrackFormat(i).getString(MediaFormat.KEY_MIME).startsWith("audio/")) return i; return -1; }
    static void extract(Context c,long id,List<Uri> sources,File output) throws Exception {
        List<MediaExtractor> inputs=new ArrayList<>(); List<MediaFormat> formats=new ArrayList<>();
        try {
            boolean aac=true; int rate=0,channels=0;
            for (Uri uri:sources) {
                check(c,id); MediaExtractor e=new MediaExtractor(); inputs.add(e); e.setDataSource(c,uri,null); int track=audio(e);
                if (track<0) throw new Exception("这个视频没有音轨，无法提取音频。");
                e.selectTrack(track); MediaFormat f=e.getTrackFormat(track); formats.add(f); aac&="audio/mp4a-latm".equals(f.getString(MediaFormat.KEY_MIME));
                if (rate==0) { rate=f.getInteger(MediaFormat.KEY_SAMPLE_RATE); channels=f.getInteger(MediaFormat.KEY_CHANNEL_COUNT); }
                else if (rate!=f.getInteger(MediaFormat.KEY_SAMPLE_RATE)||channels!=f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)) throw new Exception("分段音频参数不同，请选择完整视频后再提取。");
                if (formats.size()>1) { MediaFormat first=formats.get(0); if (first.containsKey("csd-0")&&(!f.containsKey("csd-0")||!first.getByteBuffer("csd-0").duplicate().equals(f.getByteBuffer("csd-0").duplicate()))) aac=false; }
            }
            if (inputs.isEmpty()) throw new Exception("没有可用的音频来源。");
            if (aac) remux(c,id,inputs,formats,output,rate); else transcode(c,id,inputs,formats,output,rate,channels);
            check(c,id); verify(output);
        } catch (Exception error) { output.delete(); throw error; }
        finally { for (MediaExtractor input:inputs) input.release(); }
    }
    private static void remux(Context c,long id,List<MediaExtractor> inputs,List<MediaFormat> formats,File file,int rate) throws Exception {
        MediaMuxer mux=new MediaMuxer(file.getPath(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4); boolean started=false;
        try {
            int track=mux.addTrack(formats.get(0)); mux.start(); started=true; long offset=0; ByteBuffer buffer=ByteBuffer.allocate(2*1024*1024); MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
            for (MediaExtractor input:inputs) { long first=-1,last=0; int samples=0;
                while (true) { check(c,id); buffer.clear(); int size=input.readSampleData(buffer,0); if (size<0) break;
                    if ((input.getSampleFlags()&MediaExtractor.SAMPLE_FLAG_ENCRYPTED)!=0) throw new Exception("受保护的音轨无法提取。");
                    long pts=input.getSampleTime(); if (first<0) first=pts; last=Math.max(last,pts-first); info.set(0,size,offset+last,0); mux.writeSampleData(track,buffer,info); samples++; if (!input.advance()) break;
                }
                if (samples==0) throw new Exception("音轨没有有效的声音数据。"); offset+=last+1024L*1000000/rate;
            }
            mux.stop(); started=false;
        } finally { if (started) try { mux.stop(); } catch (Exception ignored){} mux.release(); }
    }
    private static void transcode(Context c,long id,List<MediaExtractor> inputs,List<MediaFormat> formats,File file,int rate,int channels) throws Exception {
        File pcm=new File(c.getCacheDir(),"audio_"+id+".pcm");
        try {
            try (FileOutputStream out=new FileOutputStream(pcm)) {
                for (int n=0;n<inputs.size();n++) decode(c,id,inputs.get(n),formats.get(n),out,rate,channels,pcm);
            }
            encode(c,id,pcm,file,rate,channels);
        } finally { pcm.delete(); }
    }
    private static void decode(Context c,long id,MediaExtractor source,MediaFormat format,FileOutputStream out,int rate,int channels,File pcm) throws Exception {
        MediaCodec decoder=MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME));
        try {
            format.setInteger(MediaFormat.KEY_PCM_ENCODING,android.media.AudioFormat.ENCODING_PCM_16BIT); decoder.configure(format,null,null,0); decoder.start();
            boolean inputDone=false,outputDone=false; MediaCodec.BufferInfo info=new MediaCodec.BufferInfo(); long lastProgress=System.currentTimeMillis();
            while (!outputDone) {
                check(c,id); boolean progressed=false;
                if (!inputDone) { int slot=decoder.dequeueInputBuffer(10000); if (slot>=0) { ByteBuffer buffer=decoder.getInputBuffer(slot); int size=source.readSampleData(buffer,0);
                    if (size<0) { decoder.queueInputBuffer(slot,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM); inputDone=true; }
                    else { if ((source.getSampleFlags()&MediaExtractor.SAMPLE_FLAG_ENCRYPTED)!=0) throw new Exception("受保护的音轨无法提取。"); decoder.queueInputBuffer(slot,0,size,Math.max(0,source.getSampleTime()),0); source.advance(); } progressed=true; } }
                int slot=decoder.dequeueOutputBuffer(info,10000);
                if (slot==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) { MediaFormat f=decoder.getOutputFormat(); if (f.getInteger(MediaFormat.KEY_SAMPLE_RATE)!=rate||f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)!=channels||(f.containsKey(MediaFormat.KEY_PCM_ENCODING)&&f.getInteger(MediaFormat.KEY_PCM_ENCODING)!=android.media.AudioFormat.ENCODING_PCM_16BIT)) throw new Exception("当前手机无法转换这个音频格式。"); progressed=true; }
                else if (slot>=0) { ByteBuffer buffer=decoder.getOutputBuffer(slot); if (info.size>0) { buffer.position(info.offset); buffer.limit(info.offset+info.size); byte[] bytes=new byte[info.size]; buffer.get(bytes); out.write(bytes); if (pcm.length()>1024L*1024*1024) throw new Exception("音频过长，转换缓存超过 1 GB。"); }
                    outputDone=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0; decoder.releaseOutputBuffer(slot,false); progressed=true; }
                if (progressed) lastProgress=System.currentTimeMillis(); else if (System.currentTimeMillis()-lastProgress>30000) throw new Exception("音频转换超时，请重试。");
            }
        } finally { try { decoder.stop(); } catch (Exception ignored){} decoder.release(); }
    }
    private static void encode(Context c,long id,File pcm,File file,int rate,int channels) throws Exception {
        MediaCodec encoder=MediaCodec.createEncoderByType("audio/mp4a-latm"); MediaMuxer mux=null; boolean started=false;
        try (FileInputStream source=new FileInputStream(pcm)) {
            MediaFormat format=MediaFormat.createAudioFormat("audio/mp4a-latm",rate,channels); format.setInteger(MediaFormat.KEY_AAC_PROFILE,MediaCodecInfo.CodecProfileLevel.AACObjectLC); format.setInteger(MediaFormat.KEY_BIT_RATE,channels>1?192000:128000); format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE,16384);
            encoder.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE); encoder.start(); mux=new MediaMuxer(file.getPath(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4); int track=-1; boolean inputDone=false,outputDone=false; long bytes=0,lastProgress=System.currentTimeMillis(); MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
            while (!outputDone) {
                check(c,id); boolean progressed=false;
                if (!inputDone) { int slot=encoder.dequeueInputBuffer(10000); if (slot>=0) { ByteBuffer buffer=encoder.getInputBuffer(slot); int block=Math.min(buffer.capacity(),16384); block-=block%(channels*2); byte[] chunk=new byte[block]; int size=source.read(chunk); long pts=bytes/(channels*2)*1000000/rate;
                    if (size<0) { encoder.queueInputBuffer(slot,0,0,pts,MediaCodec.BUFFER_FLAG_END_OF_STREAM); inputDone=true; } else { buffer.clear(); buffer.put(chunk,0,size); encoder.queueInputBuffer(slot,0,size,pts,0); bytes+=size; } progressed=true; } }
                int slot=encoder.dequeueOutputBuffer(info,10000);
                if (slot==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) { track=mux.addTrack(encoder.getOutputFormat()); mux.start(); started=true; progressed=true; }
                else if (slot>=0) { ByteBuffer buffer=encoder.getOutputBuffer(slot); if (info.size>0&&(info.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0) { if (!started) throw new Exception("音频编码器没有输出格式。"); buffer.position(info.offset); buffer.limit(info.offset+info.size); mux.writeSampleData(track,buffer,info); }
                    outputDone=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0; encoder.releaseOutputBuffer(slot,false); progressed=true; }
                if (progressed) lastProgress=System.currentTimeMillis(); else if (System.currentTimeMillis()-lastProgress>30000) throw new Exception("音频保存超时，请重试。");
            }
            if (!started||bytes==0) throw new Exception("没有可保存的音频。"); mux.stop(); started=false;
        } finally { try { encoder.stop(); } catch (Exception ignored){} encoder.release(); if (mux!=null) { if (started) try { mux.stop(); } catch (Exception ignored){} mux.release(); } }
    }
    static void verify(File file) throws Exception {
        MediaExtractor e=new MediaExtractor(); try { e.setDataSource(file.getPath()); if (e.getTrackCount()!=1||audio(e)<0) throw new Exception("提取的文件不是独立音频。"); e.selectTrack(audio(e)); if (e.getSampleTime()<0) throw new Exception("提取的音频为空。"); } finally { e.release(); }
    }
}
