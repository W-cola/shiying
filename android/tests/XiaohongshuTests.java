import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import cn.shiying.mobile.core.Xiaohongshu;
import cn.shiying.mobile.core.MediaHeaders;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public final class XiaohongshuTests {
    static int checks;
    static void check(boolean value,String name) { if (!value) throw new AssertionError(name); checks++; }
    static JSONObject image(String url) throws Exception { return new JSONObject().put("urlDefault",url).put("width",1080).put("height",1440); }
    static final String ID="aaaaaaaaaaaaaaaaaaaaaaaa", OTHER="bbbbbbbbbbbbbbbbbbbbbbbb";
    static final String URL="https://www.xiaohongshu.com/discovery/item/"+ID+"?xsec_token=AB_test%2B%26=&xsec_source=pc_share";
    static JSONObject album() throws Exception {
        return new JSONObject().put("noteId",ID).put("type","normal").put("title","图文测试").put("desc","第一行 undefined 是正文\n第二行 😀")
            .put("user",new JSONObject().put("nickname","作者")).put("imageList",new JSONArray()
                .put(image("http://sns-webpic-qc.xhscdn.com/first!nd_dft_webp"))
                .put(image("https://sns-webpic-qc.xhscdn.com/second.jpg?sign=a%26b")));
    }
    public static void main(String[] args) throws Exception {
        check(VideoResolver.link("“88 【笔记标题】 😆 "+URL+"”").equals(URL),"Chinese quotes and share extraction");
        check(VideoResolver.link("["+URL+"”]("+URL+"”)").equals(URL),"Markdown share link deduplication");
        check(Xiaohongshu.supports("https://xhslink.com/o/abc"),"short share links");
        check(!Xiaohongshu.supports("https://xiaohongshu.com.evil.example/a"),"lookalike rejection");
        check(VideoResolver.videoId(URL).equals(ID),"note id");
        check(VideoResolver.videoId("https://www.xiaohongshu.com/explore/"+ID).equals(ID),"explore route");
        JSONObject target=album();
        JSONObject payload=new JSONObject().put("recommendation",new JSONObject(album().toString()).put("noteId",OTHER))
            .put("note",new JSONObject().put("noteDetailMap",new JSONObject().put(ID,new JSONObject().put("note",target))));
        VideoInfo info=VideoResolver.fromPayload(payload,ID,URL,URL);
        check(info!=null&&info.isImages()&&info.imageCount()==2,"album detection and all images");
        check(info.title.equals("图文测试")&&info.author.equals("作者")&&info.description.contains("undefined"),"title author caption");
        check(info.selectedAssets(info.formats.get(0)).get(1).index==2,"original image order");
        check(info.formats.get(0).assets.get(0).url.equals("https://sns-webpic-qc.xhscdn.com/first!nd_dft_webp"),"secure CDN URL, published watermark preserved");
        check(info.selectedAssets(info.formats.get(2)).size()==1&&info.selectedAssets(info.formats.get(2)).get(0).index==2,"single image selection");
        check(VideoResolver.fromPayload(payload,"cccccccccccccccccccccccc",URL,URL)==null,"never select recommendations");
        check(VideoResolver.fromPayload(payload,"",URL,URL)==null,"missing target id fails closed");
        check(VideoResolver.fromPayload(new JSONObject().put("note",new JSONObject().put("noteDetailMap",new JSONObject())),ID,URL,URL)==null,"empty login state");
        String script="<script>window.__INITIAL_STATE__="+payload.toString().replace("\"type\":\"normal\"","\"optional\":undefined,\"type\":\"normal\"")+";</script>";
        check(VideoResolver.fromHtml(script,ID,URL,URL)!=null,"JavaScript undefined state");
        check(VideoResolver.fromHtml(script,ID,URL,URL).description.contains("undefined"),"don't rewrite quoted caption text");
        check(Xiaohongshu.textDocument(info).contains("第一行 undefined 是正文\n第二行 😀"),"UTF8 multiline caption");
        check(!Xiaohongshu.textDocument(info).contains("xsec_token")&&!Xiaohongshu.textDocument(info).contains("AB_test"),"no signed tokens in exported text");
        VideoInfo restored=VideoInfo.fromJson(info.toJson());
        check(restored.isImages()&&restored.imageCount()==2&&restored.description.equals(info.description),"rotation state preservation");
        JSONObject stream=new JSONObject().put("h264",new JSONArray()
            .put(new JSONObject().put("masterUrl","http://sns-video-bd.xhscdn.com/low.mp4").put("width",640).put("height",360).put("duration",12000))
            .put(new JSONObject().put("masterUrl","https://sns-video-bd.xhscdn.com/high.mp4").put("width",1920).put("height",1080).put("duration",12000)));
        JSONObject movie=new JSONObject().put("noteId",ID).put("type","video").put("title","视频测试").put("imageList",target.getJSONArray("imageList"))
            .put("video",new JSONObject().put("media",new JSONObject().put("stream",stream)));
        VideoInfo video=VideoResolver.fromPayload(movie,ID,URL,URL);
        check(video!=null&&!video.isImages()&&video.formats.size()==2&&video.formats.get(0).height==1080&&video.duration==12,"video streams and quality sorting");
        check(VideoResolver.fromPayload(new JSONObject(movie.toString()).put("video",new JSONObject()),ID,URL,URL)==null,"video cover never becomes an image album");
        check(VideoResolver.fromPayload(new JSONObject(target.toString()).put("imageList",new JSONArray().put(image("https://cdn.example/one.jpg")).put(image(""))),ID,URL,URL)==null,"incomplete album is rejected");
        check(Xiaohongshu.mediaUrl("http://xhscdn.com.evil.example/one.jpg").isEmpty(),"no insecure lookalike upgrades");
        byte[] jpg={(byte)255,(byte)216,(byte)255,1};
        byte[] png={(byte)137,80,78,71,13,10,26,10};
        byte[] webp="RIFF0000WEBPVP8 ".getBytes(StandardCharsets.ISO_8859_1);
        byte[] mp4={0,0,0,24,102,116,121,112,105,115,111,109};
        check(MediaHeaders.detect(jpg,jpg.length,"image").mime.equals("image/jpeg"),"JPEG header");
        check(MediaHeaders.detect(png,png.length,"image").ext.equals("png"),"PNG header");
        check(MediaHeaders.detect(webp,webp.length,"image").ext.equals("webp"),"WebP header");
        check(MediaHeaders.detect(mp4,mp4.length,"video").mime.equals("video/mp4"),"video regression header");
        check(MediaHeaders.detect(mp4,mp4.length,"image")==null,"wrong media type rejection");
        byte[] html="<html>ftyp please log in</html>".getBytes(StandardCharsets.UTF_8);
        check(MediaHeaders.detect(html,html.length,"")==null,"login pages are never downloaded as media");
        if (args.length>0) {
            JSONArray links=new JSONArray(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8));
            JSONArray results=new JSONArray();
            for (int i=0;i<links.length();i++) {
                String url=links.getString(i); JSONObject result=new JSONObject().put("id",Xiaohongshu.id(url));
                try {
                    VideoResolver resolver=new VideoResolver(u->"",s->{}); VideoInfo live=resolver.resolve(url);
                    result.put("state","resolved").put("title",live.title).put("kind",live.kind).put("formats",live.formats.size());
                    VideoResolver.Page media=resolver.probe(live,live.formats.get(0)); result.put("mime",media.mime);
                } catch (VideoResolver.NeedsBrowser e) {
                    result.put("state","browser_login_or_verification_required").put("target_preserved",e.id.equals(Xiaohongshu.id(url))).put("source_token_preserved",e.url.contains("xsec_token="));
                    check(e.id.equals(Xiaohongshu.id(url))&&e.url.contains("xsec_token="),"live restricted note keeps correct target and source URL");
                }
                results.put(result);
            }
            if (args.length>1) Files.write(Paths.get(args[1]),new JSONObject().put("checks",checks).put("links",results).toString(2).getBytes(StandardCharsets.UTF_8));
        }
        System.out.println("Passed "+checks+" Xiaohongshu media checks.");
    }
}
