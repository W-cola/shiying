import cn.shiying.mobile.core.VideoInfo;
import cn.shiying.mobile.core.VideoResolver;
import org.json.JSONObject;
import java.net.URLEncoder;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;

public final class CoreTests {
    private static int checks;
    private static void check(boolean condition,String name) { if (!condition) throw new AssertionError(name); checks++; }
    private static JSONObject item(String id,int height) throws Exception {
        return new JSONObject().put("aweme_id",id).put("desc","视频 "+id).put("author",new JSONObject().put("nickname","作者"))
            .put("video",new JSONObject().put("width",720).put("height",height).put("duration",12300)
                .put("play_addr",new JSONObject().put("url_list",new org.json.JSONArray().put("https://cdn.example/"+id+".mp4"))));
    }
    public static void main(String[] args) throws Exception {
        String share="0.76 07/21 yGv:/ u@F.uF :8pm https://v.douyin.com/78nnhuQHT8k/ 复制此链接，打开Dou音搜索，直接观看视频！";
        check(VideoResolver.link(share).equals("https://v.douyin.com/78nnhuQHT8k/"),"share text extraction");
        check(VideoResolver.link("https://cdn.example/v.mp4?token=a%26b%2Bc#ignore").equals("https://cdn.example/v.mp4?token=a%26b%2Bc"),"signed query preservation");
        check(VideoResolver.isDouyin("https://v.douyin.com/a"),"douyin hostname");
        check(!VideoResolver.isDouyin("https://douyin.com.example.org/a"),"lookalike hostname");
        check(VideoResolver.videoId("https://www.douyin.com/?modal_id=123").equals("123"),"modal id");
        check(VideoResolver.videoId("https://www.iesdouyin.com/share/video/123/").equals("123"),"share id");
        boolean invalid=false; try { VideoResolver.link("没有链接"); } catch (Exception e) { invalid=true; } check(invalid,"invalid input");
        invalid=false; try { VideoResolver.link("https://user:password@example.org/v.mp4"); } catch (Exception e) { invalid=true; } check(invalid,"embedded credentials");
        invalid=false; try { VideoResolver.link("https://a.example/1 https://b.example/2"); } catch (Exception e) { invalid=true; } check(invalid,"multiple links");
        JSONObject payload=new JSONObject().put("recommendation",item("999",1080)).put("detail",item("123",1280));
        VideoInfo video=VideoResolver.fromPayload(payload,"123","https://v.douyin.com/a","https://www.douyin.com/video/123");
        check(video!=null&&video.id.equals("123")&&video.title.equals("视频 123"),"target over recommendations");
        check(video.duration==12.3&&video.author.equals("作者"),"metadata");
        check(VideoResolver.fromPayload(payload,"456","","")==null,"missing target rejection");
        String encoded=URLEncoder.encode(payload.toString(),"UTF-8").replace("+","%20");
        check(VideoResolver.fromHtml("<script id='RENDER_DATA'>"+encoded+"</script>","123","","")!=null,"render data decoding");
        check(VideoResolver.fromHtml("<script>window._ROUTER_DATA = "+payload+";</script>","123","","")!=null,"router data decoding");
        check(!VideoResolver.filename("../../视频:\"<>|?*","../123").contains("/"),"filename safety");
        check(VideoInfo.fromJson(video.toJson()).formats.get(0).url.equals(video.formats.get(0).url),"state restoration");
        String mobileShare="“4.89 复制打开抖音，看看【平均Mister的作品】# 发布会  https://v.douyin.com/xP--46iFdBs/ 04/13 O@K.jC :6pm QxF:/ ”";
        check(VideoResolver.link(mobileShare).equals("https://v.douyin.com/xP--46iFdBs/"),"Android client whole-share text and hyphenated short link");
        check(VideoResolver.videoId("https://www.iesdouyin.com/share/video/7693747185347940454/?utm_medium=android&share_sign=abc").equals("7693747185347940454"),"Android client redirect with tracking query");
        check(VideoResolver.mediaUrl("http://v26-web.douyinvod.com/v.mp4?token=a%26b%2Bc").equals("https://v26-web.douyinvod.com/v.mp4?token=a%26b%2Bc"),"published HTTP CDN URL upgraded without altering its signed query");
        check(VideoResolver.mediaUrl("http://douyinvod.com.evil.example/v.mp4").isEmpty(),"do not upgrade unrelated insecure hosts");
        check(VideoResolver.mediaUrl("//v26-web.douyinvod.com/v.mp4").startsWith("https://"),"protocol-relative CDN URL");
        JSONObject mobile=item("123",1280);
        mobile.getJSONObject("video").getJSONObject("play_addr").put("url_list",new org.json.JSONArray().put("http://v26-web.douyinvod.com/123.mp4").put("https://v3-web.douyinvod.com/123.mp4"));
        VideoInfo cdn=VideoResolver.fromPayload(mobile,"123","https://v.douyin.com/short","https://www.douyin.com/video/123");
        check(cdn!=null&&cdn.formats.get(0).url.startsWith("https://")&&cdn.formats.get(0).alternatives.size()==1,"mobile payload keeps published backup CDN");
        check(cdn.selectedAssets(cdn.formats.get(0)).get(0).alternatives.size()==1,"download selection carries fallback CDN");
        check(VideoInfo.fromJson(cdn.toJson()).formats.get(0).alternatives.size()==1,"fallback CDN survives activity recreation");
        check(VideoResolver.fromHtml("<script>window._SSR_DATA = "+mobile+";</script>","123","https://v.douyin.com/short","")!=null,"mobile SSR state script");
        check(VideoResolver.fromPayload(payload,"","https://v.douyin.com/short","https://www.douyin.com/")==null,"no target id means no recommendation selection");
        if (args.length>0) {
            VideoResolver resolver=new VideoResolver(url -> "",System.out::println);
            VideoInfo live=resolver.resolve(share);
            check(live.id.equals("7693840282563565674"),"live target match");
            check(!live.formats.isEmpty()&&live.formats.get(0).width==854,"live video source");
            VideoResolver.Page media=resolver.probe(live,live.formats.get(0));
            check("mp4".equals(media.ext),"live MP4 header verification");
            JSONObject report=new JSONObject().put("id",live.id).put("title",live.title).put("author",live.author)
                .put("duration",live.duration).put("formats",live.formats.size()).put("width",live.formats.get(0).width)
                .put("height",live.formats.get(0).height).put("media","MP4 header verified").put("checks",checks);
            Files.write(Paths.get(args[0]),report.toString(2).getBytes(StandardCharsets.UTF_8));
        }
        System.out.println("Passed "+checks+" native Android core checks.");
    }
}
