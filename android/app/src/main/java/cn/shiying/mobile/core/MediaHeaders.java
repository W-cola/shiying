package cn.shiying.mobile.core;

import java.nio.charset.StandardCharsets;

/** Shared preflight/completion checks; HTML and JSON cannot masquerade as media files. */
public final class MediaHeaders {
    public static final class Type {
        public final String kind,ext,mime;
        Type(String kind,String ext,String mime) { this.kind=kind; this.ext=ext; this.mime=mime; }
    }
    public static Type detect(byte[] bytes,int length,String expected) {
        int n=Math.min(length,bytes.length); if (n<3) return null;
        String prefix=new String(bytes,0,Math.min(n,64),StandardCharsets.ISO_8859_1);
        Type type=null;
        if ((bytes[0]&255)==0xff&&(bytes[1]&255)==0xd8&&(bytes[2]&255)==0xff) type=new Type("image","jpg","image/jpeg");
        else if (n>=8&&(bytes[0]&255)==0x89&&prefix.startsWith("\u0089PNG\r\n\u001a\n")) type=new Type("image","png","image/png");
        else if (n>=12&&prefix.startsWith("RIFF")&&prefix.substring(8).startsWith("WEBP")) type=new Type("image","webp","image/webp");
        else if (prefix.startsWith("GIF87a")||prefix.startsWith("GIF89a")) type=new Type("image","gif","image/gif");
        else if (n>=12&&prefix.substring(4,8).equals("ftyp")) {
            if (prefix.contains("avif")||prefix.contains("avis")) type=new Type("image","avif","image/avif");
            else if (prefix.contains("heic")||prefix.contains("heix")||prefix.contains("mif1")) type=new Type("image","heic","image/heic");
            else type=new Type("video","mp4","video/mp4");
        } else if (n>=4&&(bytes[0]&255)==0x1a&&(bytes[1]&255)==0x45&&(bytes[2]&255)==0xdf&&(bytes[3]&255)==0xa3) type=new Type("video","webm","video/webm");
        return type!=null&&(expected==null||expected.isEmpty()||expected.equals(type.kind))?type:null;
    }
}
