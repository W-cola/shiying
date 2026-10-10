package cn.shiying.mobile;

import org.json.JSONArray;
import org.json.JSONObject;

public final class AlbumRecordTests {
    static int checks;
    static void check(boolean value,String message) { if (!value) throw new AssertionError(message); checks++; }
    static JSONObject item(long id,int index,String stamp,String batch) {
        String suffix=index==0?"正文":String.format(java.util.Locale.ROOT,"%03d",index);
        JSONObject value=new JSONObject().put("id",id).put("title","同一条图文 · "+(index==0?"正文":"图片 "+index+"/3"))
            .put("source","https://example.test/post/1").put("noteId","post1").put("file","同一条图文 [post1] "+stamp+"_"+suffix+(index==0?".txt":".jpg"))
            .put("mime",index==0?"text/plain":"image/jpeg");
        if (!batch.isEmpty()) value.put("albumBatch",batch).put("albumTitle","同一条图文"); return value;
    }
    public static void main(String[] args) {
        JSONArray records=new JSONArray().put(item(3,3,"20261008_100000_000",""))
            .put(item(-10,0,"20261008_100000_000","")).put(item(1,1,"20261008_100000_000","")).put(item(2,2,"20261008_100000_000",""));
        JSONObject video=new JSONObject().put("id",99).put("mime","video/mp4").put("title","视频"); records.put(video);
        JSONArray grouped=AlbumRecords.groups(records); check(grouped.length()==2,"One old album plus unchanged video"); JSONObject album=grouped.getJSONObject(0);
        check(AlbumRecords.isAlbum(album),"Legacy names recognized as a collection"); check(album.getString("title").equals("同一条图文"),"Child suffix removed from parent title");
        check(album.getJSONArray("items").length()==4,"Caption kept inside collection"); check(AlbumRecords.images(album).length()==3,"All pictures retained");
        check(AlbumRecords.images(album).getJSONObject(0).getLong("id")==1,"Picture one comes first"); check(AlbumRecords.images(album).getJSONObject(2).getLong("id")==3,"Picture order follows original index");
        check(AlbumRecords.text(album).getLong("id")==-10,"Caption found independently of file order"); check(grouped.getJSONObject(1)==video,"Video object and metadata untouched");
        records.put(item(4,1,"20261008_100001_000","")); check(AlbumRecords.groups(records).length()==3,"Different download of same link is independent");
        JSONObject first=item(7,2,"20261008_100000_000","a").put("imageIndex",2),second=item(8,1,"20261008_100000_000","a").put("imageIndex",1);
        JSONArray newJobs=new JSONArray().put(first).put(second).put(item(9,3,"20261008_100000_000","b")); JSONArray newGroups=AlbumRecords.groups(newJobs);
        check(newGroups.length()==2,"Explicit batches cannot accidentally merge"); check(newGroups.getJSONObject(0).getInt("imageCount")==2,"Selected pictures are counted accurately");
        check(AlbumRecords.images(newGroups.getJSONObject(0)).getJSONObject(0)==second,"New batch index order preserved");
        JSONObject plain=new JSONObject().put("id",17).put("mime","image/jpeg").put("file","ordinary.jpg");
        check(AlbumRecords.groups(new JSONArray().put(plain)).getJSONObject(0)==plain,"Unrelated standalone picture untouched");
        JSONObject text=item(18,0,"20261008_110000_000",""); check(!AlbumRecords.isAlbum(AlbumRecords.groups(new JSONArray().put(text)).getJSONObject(0)),"Orphan caption remains accessible");
        check(records.length()==6,"Grouping does not modify underlying file records");
        System.out.println("Passed "+checks+" album grouping checks.");
    }
}
