import cn.shiying.mobile.core.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;

public final class PlatformTests {
    static int checks;
    static void check(boolean value,String name) { if (!value) throw new AssertionError(name); checks++; }
    static JSONObject picture(String url) throws Exception { return new JSONObject().put("url",url).put("width",1080).put("height",1440); }
    static JSONObject media(String url,String codec,int id) throws Exception { return new JSONObject().put("baseUrl",url).put("codecs",codec).put("id",id).put("width",640).put("height",360).put("bandwidth",10000); }
    public static void main(String[] args) throws Exception {
        check(VideoResolver.link("复制打开 https://v.kuaishou.com/AbC123/ 看视频").equals("https://v.kuaishou.com/AbC123/"),"Kuaishou complete mobile share text");
        check(VideoResolver.link("哔哩哔哩 http://b23.tv/AbC123").equals("https://b23.tv/AbC123"),"known HTTP shares upgrade to HTTPS");
        check(Platforms.name("https://channels.weixin.qq.com/mobile-support/pages/interaction/interaction.html?objectId=123").equals("视频号"),"Channels public web shares");
        check(Platforms.known("https://weixin.qq.com/sph/AwuKEvusQH")&&!Platforms.known("https://weixin.qq.com/other/page")&&!Platforms.known("https://weixin.qq.com.evil.test/sph/x"),"Channels sph short links only on official host/path");
        check(VideoResolver.videoId("https://channels.weixin.qq.com/finder-preview/pages/sph?id=AwuKEvusQH").equals("AwuKEvusQH"),"Sph preview keeps its share identifier");
        check(VideoResolver.link("https\\://v.kuaishou.com/KyQPissP 复制分享").equals("https://v.kuaishou.com/KyQPissP"),"Markdown-escaped share separator normalized");
        check(ChannelsService.shareId("https://weixin.qq.com/sph/A3loS34sJs?from=share").equals("A3loS34sJs"),"Anonymous resolver accepts the exact sph share ID");
        check(!ChannelsService.supports("https://weixin.qq.com.evil.test/sph/abc")&&!ChannelsService.supports("https://user@weixin.qq.com/sph/abc")&&!ChannelsService.supports("https://weixin.qq.com/other/abc"),"Resolver does not submit other domains or credential URLs");
        String share="https://weixin.qq.com/sph/A3loS34sJs";
        JSONObject resolved=new JSONObject().put("ok",true).put("data",new JSONObject().put("media_type",4).put("author","作者").put("description","目标视频\n正文").put("cover_url","https://finder.video.qq.com/cover.jpg").put("h264_url","https://finder.video.qq.com/movie.mp4?token=sample").put("h265_url","https://finder.video.qq.com/movie-hevc.mp4"));
        VideoInfo serviceVideo=ChannelsService.fromResponse(resolved,share);
        check(serviceVideo!=null&&serviceVideo.id.equals("A3loS34sJs")&&serviceVideo.sourceUrl.equals(share)&&serviceVideo.formats.size()==2,"Resolved media remains bound to the submitted share");
        check(serviceVideo.formats.get(0).label.contains("H.264")&&serviceVideo.formats.get(0).url.endsWith("token=sample"),"H264 default and signed URL preserved");
        check(ChannelsService.fromResponse(new JSONObject(resolved.toString()).put("ok",false),share)==null,"Service failures do not produce media");
        JSONObject imageResponse=new JSONObject(resolved.toString()); imageResponse.getJSONObject("data").put("media_type",2);
        check(ChannelsService.fromResponse(imageResponse,share)==null,"Unsupported service image data cannot become a video");
        JSONObject untrusted=new JSONObject(resolved.toString()); untrusted.getJSONObject("data").put("h264_url","https://example.test/other.mp4").put("h265_url","");
        check(ChannelsService.fromResponse(untrusted,share)==null,"Unrelated media servers rejected");
        untrusted.getJSONObject("data").put("h264_url","https://finder.video.qq.com/cover.jpg");
        check(ChannelsService.fromResponse(untrusted,share)==null,"A cover address cannot masquerade as video");
        JSONObject duplicate=new JSONObject(resolved.toString()); duplicate.getJSONObject("data").put("h265_url",duplicate.getJSONObject("data").getString("h264_url"));
        check(ChannelsService.fromResponse(duplicate,share).formats.size()==1,"Duplicate source URLs removed");
        check(!Platforms.known("https://kuaishou.com.evil.example/a"),"strict host matching");
        check(VideoResolver.videoId("https://m.bilibili.com/video/BV1GJ411x7h7?p=2").equals("BV1GJ411x7h7"),"mobile BV target");
        check(VideoResolver.videoId("https://www.bilibili.com/video/av170001").equals("av170001"),"legacy AV target");
        check(VideoResolver.videoId("https://t.bilibili.com/123456789").equals("opus123456789"),"Bilibili dynamic target");
        check(VideoResolver.videoId("https://www.kuaishou.com/short-video/3xabcd").equals("3xabcd"),"desktop Kuaishou target");
        check(VideoResolver.videoId("https://app.kuaishou.com/fw/photo/3xabcd?share=1").equals("3xabcd"),"mobile Kuaishou target");
        check(Platforms.samePlatform("https://v.m.chenzhongtech.com/fw/photo/3xabcd","https://www.kuaishou.com/short-video/3xabcd")&&VideoResolver.videoId("https://v.m.chenzhongtech.com/fw/photo/3xabcd").equals("3xabcd"),"Kuaishou alternate official mobile-share domain");
        check(VideoResolver.videoId("https://channels.weixin.qq.com/feed/abc?objectId=12345678901234567890").equals("12345678901234567890"),"Channels string identifiers keep precision");
        check(VideoResolver.videoId("https://www.douyin.com/note/12345").equals("12345"),"Douyin desktop note target");
        check(VideoResolver.videoId("https://www.iesdouyin.com/share/slides/12345/").equals("12345"),"Douyin mobile slides target");
        JSONObject dy=new JSONObject().put("aweme_id","12345").put("desc","图文正文\n第二行").put("images",new JSONArray()
            .put(new JSONObject().put("url_list",new JSONArray().put("http://p3.douyinpic.com/first.webp")))
            .put(new JSONObject().put("display_image",new JSONObject().put("url_list",new JSONArray().put("https://p3.douyinpic.com/second.webp")))));
        VideoInfo album=VideoResolver.fromPayload(dy,"12345","https://v.douyin.com/short","https://www.douyin.com/note/12345");
        check(album!=null&&album.isImages()&&album.imageCount()==2,"Douyin image albums");
        check(album.formats.get(0).assets.get(0).url.startsWith("https://"),"Douyin picture CDN upgrade");
        check(album.formats.get(2).assets.get(0).index==2,"single image and preserved order");
        check(VideoResolver.fromPayload(dy,"99","https://v.douyin.com/a","https://www.douyin.com/note/99")==null,"Douyin recommendation rejection");
        String bv="BV1GJ411x7h7",page="https://www.bilibili.com/video/"+bv+"?p=2";
        JSONObject meta=new JSONObject().put("bvid",bv).put("aid",170001).put("title","B站测试").put("pages",new JSONArray().put(new JSONObject().put("cid",11)).put(new JSONObject().put("cid",22)));
        JSONObject play=new JSONObject().put("data",new JSONObject().put("dash",new JSONObject().put("video",new JSONArray().put(media("https://upos.bilivideo.com/v.m4s","avc1.64001E",32)))
            .put("audio",new JSONArray().put(media("https://upos.bilivideo.com/a.m4s","mp4a.40.2",30232)))));
        JSONObject root=new JSONObject().put("biliPage",page).put("metadata",meta).put("playInfo",play).put("requestUrl","https://api.bilibili.com/x/player/playurl?bvid="+bv+"&cid=22");
        VideoInfo movie=VideoResolver.fromPayload(root,bv,page,page);
        check(movie!=null&&movie.formats.get(0).mode.equals("dash"),"DASH playback uses native assembly");
        check(movie.formats.get(0).assets.size()==2&&movie.formats.get(0).assets.get(1).kind.equals("audio"),"DASH video always paired with sound");
        check(VideoInfo.fromJson(movie.toJson()).formats.get(0).mode.equals("dash"),"assembly mode survives rotation");
        JSONObject wrong=new JSONObject(root.toString()).put("requestUrl","https://api.bilibili.com/x/player/playurl?bvid="+bv+"&cid=11");
        check(VideoResolver.fromPayload(wrong,bv,page,page)==null,"different P CID is rejected");
        check(VideoResolver.fromPayload(new JSONObject(root.toString()).put("biliPage","https://www.bilibili.com/video/BV1xx411c7mD"),bv,page,page)==null,"wrong Bilibili page is rejected");
        JSONObject unpaid=new JSONObject(play.toString()); unpaid.getJSONObject("data").put("is_preview",1);
        check(VideoResolver.fromPayload(new JSONObject(root.toString()).put("playInfo",unpaid),bv,page,page)==null,"paid preview is not a complete video");
        check(VideoResolver.fromPayload(new JSONObject().put("metadata",meta).put("recommendation",play),bv,page,page)==null,"playback without provenance is rejected");
        String html="<script>window.__INITIAL_STATE__="+meta+";</script><script>window.__playinfo__="+play+";</script>";
        check(VideoResolver.fromHtml(html,bv,page,page)!=null,"paired Bilibili SSR scripts");
        JSONObject dynamic=new JSONObject().put("id_str","123456789").put("modules",new JSONObject().put("module_dynamic",new JSONObject().put("desc",new JSONObject().put("text","动态正文"))
            .put("major",new JSONObject().put("draw",new JSONObject().put("items",new JSONArray().put(picture("https://i0.hdslb.com/a.jpg")).put(picture("https://i0.hdslb.com/b.jpg")))))));
        check(VideoResolver.fromPayload(dynamic,"opus123456789","https://t.bilibili.com/123456789","https://www.bilibili.com/opus/123456789").imageCount()==2,"Bilibili picture dynamic");
        JSONObject ks=new JSONObject().put("photoId","3xabcd").put("caption","快手视频").put("playUrl","https://txmov.a.kwimgs.com/movie.mp4");
        check(VideoResolver.fromPayload(ks,"3xabcd","https://v.kuaishou.com/short","https://www.kuaishou.com/short-video/3xabcd")!=null,"Kuaishou published video");
        ks.remove("playUrl"); ks.put("atlas",new JSONObject().put("cdn","https://tx.a.kwimgs.com").put("list",new JSONArray().put("first.jpg").put("second.jpg")));
        VideoInfo ksAlbum=VideoResolver.fromPayload(ks,"3xabcd","https://v.kuaishou.com/short","https://www.kuaishou.com/short-video/3xabcd");
        check(ksAlbum!=null&&ksAlbum.imageCount()==2&&ksAlbum.formats.get(0).assets.get(1).url.endsWith("/second.jpg"),"Kuaishou published atlas");
        check(VideoResolver.fromPayload(ks,"other","https://v.kuaishou.com/short","https://www.kuaishou.com/short-video/other")==null,"Kuaishou target mismatch");
        String ksPage="https://www.kuaishou.com/short-video/3xabcd";
        JSONObject representation=new JSONObject().put("height",720).put("width",1280).put("url",new JSONObject().put("json",new JSONArray().put("https://txmov.a.kwimgs.com/cache.mp4")));
        JSONObject cache=new JSONObject().put("VisionVideoDetailPhoto:3xabcd",new JSONObject().put("caption","缓存目标").put("manifest",new JSONObject().put("type","id").put("id","manifest-fixture")))
            .put("manifest-fixture",new JSONObject().put("adaptationSet",new JSONArray().put(new JSONObject().put("__ref","set-fixture")))).put("set-fixture",new JSONObject().put("representation",new JSONArray().put(representation)));
        VideoInfo cached=VideoResolver.fromPayload(new JSONObject().put("defaultClient",cache),"3xabcd",ksPage,ksPage);
        check(cached!=null&&cached.formats.get(0).height==720,"Kuaishou normalized Apollo cache and published references");
        check(VideoResolver.fromPayload(new JSONObject().put("defaultClient",cache),"other",ksPage,ksPage)==null,"Apollo cache cannot select a different target");
        cache.getJSONObject("VisionVideoDetailPhoto:3xabcd").put("photoId","other");
        check(VideoResolver.fromPayload(new JSONObject().put("defaultClient",cache),"3xabcd",ksPage,ksPage)==null,"Explicit conflicting cache target rejected");
        JSONObject appPhoto=new JSONObject().put("photoId","3xabcd").put("photo",new JSONObject().put("mainMvUrls",new JSONArray().put(new JSONObject().put("url","https://txmov.a.kwimgs.com/mobile.mp4"))));
        check(VideoResolver.fromPayload(appPhoto,"3xabcd",ksPage,ksPage)!=null,"Kuaishou mobile mainMvUrls data");
        JSONArray atlasList=new JSONArray().put(new JSONObject().put("cdnUrls",new JSONArray().put(picture("https://tx.a.kwimgs.com/1.jpg")).put(picture("https://tx.a.kwimgs.com/backup.jpg")))).put(picture("https://tx.a.kwimgs.com/2.jpg"));
        JSONObject atlasPhoto=new JSONObject().put("photoId","3xabcd").put("photoType","ATLAS").put("ext_params",new JSONObject().put("atlas",atlasList).toString());
        VideoInfo cachedAlbum=VideoResolver.fromPayload(atlasPhoto,"3xabcd",ksPage,ksPage);
        check(cachedAlbum!=null&&cachedAlbum.imageCount()==2,"Kuaishou serialized atlas takes one CDN per image, not backup duplicates");
        JSONObject numericPhoto=new JSONObject().put("photoId","5193494998946082133").put("share_info","userId=user&photoId=3xabcd").put("userName","正确作者").put("mainMvUrls",new JSONArray().put(new JSONObject().put("url","https://txmov.a.kwimgs.com/bound.mp4")));
        VideoInfo aliasVideo=VideoResolver.fromPayload(new JSONObject().put("photo",numericPhoto),"3xabcd",ksPage,ksPage+"?shareObjectId=5193494998946082133");
        check(aliasVideo!=null&&aliasVideo.id.equals("3xabcd")&&aliasVideo.author.equals("正确作者"),"Kuaishou numeric media ID requires published share alias");
        check(VideoResolver.fromPayload(new JSONObject().put("photo",numericPhoto),"3xabcd",ksPage,ksPage+"?shareObjectId=111")==null,"Conflicting numeric share identifier rejected");
        numericPhoto.remove("mainMvUrls"); numericPhoto.put("photoType","HORIZONTAL_ATLAS");
        JSONObject hostAtlas=new JSONObject().put("cdn",new JSONArray().put("p23.a.yximgs.com").put("p2.a.yximgs.com")).put("cdnList",new JSONArray().put(new JSONObject().put("cdn","p23.a.yximgs.com"))).put("list",new JSONArray().put("/ufile/first.jpg").put("/ufile/second.jpg")).put("size",new JSONArray().put(new JSONObject().put("w",1080).put("h",1440)));
        VideoInfo mobileAlbum=VideoResolver.fromPayload(new JSONObject().put("photo",numericPhoto).put("atlas",hostAtlas),"3xabcd",ksPage,ksPage);
        check(mobileAlbum!=null&&mobileAlbum.imageCount()==2&&mobileAlbum.formats.get(0).assets.get(0).url.equals("https://p23.a.yximgs.com/ufile/first.jpg"),"Mobile atlas reads published host arrays and relative paths");
        check(mobileAlbum.formats.get(0).assets.get(0).alternatives.size()==1&&mobileAlbum.formats.get(1).width==1080,"Picture fallback CDN and dimensions preserved");
        String sph="https://channels.weixin.qq.com/finder-preview/pages/sph?id=short";
        JSONObject preview=new JSONObject().put("previewPage",sph).put("feedInfo",new JSONObject().put("description","分享内容").put("coverUrl","https://qpic.cn/cover.jpg")).put("authorInfo",new JSONObject().put("nickname","作者"));
        check(VideoResolver.fromPayload(preview,"short","https://weixin.qq.com/sph/short",sph)==null,"Preview-only cover must not become downloadable video or picture post");
        preview.getJSONObject("feedInfo").put("h264VideoInfo",new JSONObject().put("videoUrl","https://finder.video.qq.com/v.mp4"));
        check(VideoResolver.fromPayload(preview,"short","https://weixin.qq.com/sph/short",sph)!=null,"Published preview video playback DTO accepted with exact page provenance");
        check(VideoResolver.fromPayload(preview,"other","https://weixin.qq.com/sph/other",sph)==null,"Different preview share rejected");
        preview.getJSONObject("feedInfo").remove("h264VideoInfo"); preview.getJSONObject("feedInfo").put("picInfo",new JSONArray().put(picture("https://mmbiz.qpic.cn/1.jpg")).put(picture("https://mmbiz.qpic.cn/2.jpg")));
        check(VideoResolver.fromPayload(preview,"short","https://weixin.qq.com/sph/short",sph).imageCount()==2,"Explicit preview picture list supported");
        JSONObject wx=new JSONObject().put("objectId","123").put("objectDesc",new JSONObject().put("description","视频号正文").put("media",new JSONArray().put(new JSONObject().put("mediaType",4).put("url","https://finder.video.qq.com/v.mp4").put("decodeKey","0"))));
        String wxPage="https://channels.weixin.qq.com/feed/123?objectId=123&nonceId=secret";
        check(VideoResolver.fromPayload(wx,"123",wxPage,wxPage)!=null,"Channels ordinary published MP4");
        wx.getJSONObject("objectDesc").getJSONArray("media").getJSONObject(0).put("decodeKey","123456789");
        VideoInfo encoded=VideoResolver.fromPayload(wx,"123",wxPage,wxPage);
        check(encoded!=null&&encoded.formats.get(0).mode.equals("channels")&&encoded.formats.get(0).assets.get(0).decodeKey.equals("123456789"),"published Channels playback parameter schedules format conversion");
        wx.getJSONObject("objectDesc").getJSONArray("media").getJSONObject(0).put("drm",true);
        check(VideoResolver.fromPayload(wx,"123",wxPage,wxPage)==null,"DRM remains unsupported even with a playback parameter");
        wx.getJSONObject("objectDesc").put("media",new JSONArray().put(new JSONObject().put("mediaType",2).put("url","https://mmbiz.qpic.cn/one.jpg")).put(new JSONObject().put("mediaType",2).put("url","https://mmbiz.qpic.cn/two.jpg")));
        VideoInfo wxAlbum=VideoResolver.fromPayload(wx,"123",wxPage,wxPage);
        check(wxAlbum!=null&&wxAlbum.imageCount()==2,"Channels image feed");
        check(!Albums.text(wxAlbum).contains("nonceId")&&Albums.text(wxAlbum).contains("平台：视频号"),"neutral caption export excludes access query");
        check(VideoResolver.fromHtml("<script>window.__APOLLO_STATE__=JSON.parse("+JSONObject.quote(ks.toString())+");</script>","3xabcd","https://www.kuaishou.com/short-video/3xabcd","https://www.kuaishou.com/short-video/3xabcd")!=null,"Kuaishou serialized Apollo state");
        String[] keys={"0","123456789","18446744073709551615"};
        String[] digests={"e1662af3b7e59867c919ad19055fc8cecea2b154d37e1459b2f96d1da14cef1f","1f972db9d304b9c779a59f9830f1b03c98e247a4e1102d926996dd61b60d8e67","5afbffd76305e81467f97c6370fa07916e9b197611bf5c357a854eb92a6354a1"};
        for (int i=0;i<keys.length;i++) {
            byte[] bytes=new byte[ChannelsCodec.PREFIX]; new ChannelsCodec(keys[i]).apply(bytes,0,bytes.length);
            byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(bytes); StringBuilder hex=new StringBuilder(); for (byte b:hash) hex.append(String.format("%02x",b&255));
            check(hex.toString().equals(digests[i]),"ISAAC64 matches independent unsigned reference vector "+i);
            byte[] chunks=new byte[ChannelsCodec.PREFIX+12]; ChannelsCodec chunked=new ChannelsCodec(keys[i]);
            for (int at=0;at<chunks.length;at+=37) chunked.apply(chunks,at,Math.min(37,chunks.length-at));
            check(java.util.Arrays.equals(bytes,java.util.Arrays.copyOf(chunks,bytes.length))&&chunks[chunks.length-1]==0,"stream boundaries and unchanged suffix "+i);
        }
        String article="<title>专栏测试</title><div class='article-holder'><figure><img src='data:blank' data-src='https://i0.hdslb.com/body.jpg'></figure></div>article-footer";
        check(VideoResolver.fromHtml(article,"cv123","https://www.bilibili.com/read/cv123","https://www.bilibili.com/read/cv123").imageCount()==1,"Bilibili article body excludes placeholder images");
        if (args.length>0) {
            JSONArray results=new JSONArray();
            for (String link:new String[]{"https://www.bilibili.com/video/BV1GJ411x7h7","https://www.bilibili.com/video/av170001"}) {
                VideoResolver resolver=new VideoResolver(u->"",s->{}); VideoInfo live=resolver.resolve(link); check(live.platform.equals("B站")&&!live.formats.isEmpty(),"live Bilibili target");
                VideoResolver.Page probe=resolver.probe(live,live.formats.get(0)); check(probe.mime.equals("video/mp4"),"live Bilibili media header");
                results.put(new JSONObject().put("id",live.id).put("formats",live.formats.size()).put("first_mode",live.formats.get(0).mode).put("title",live.title).put("media_header","verified"));
            }
            Files.write(Paths.get(args[0]),new JSONObject().put("checks",checks).put("links",results).toString(2).getBytes(StandardCharsets.UTF_8));
        }
        System.out.println("Passed "+checks+" multi-platform checks.");
    }
}
