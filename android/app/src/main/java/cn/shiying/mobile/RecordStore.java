package cn.shiying.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;

/** Keep successful deletions from being restored by a late activity save or rotation. */
final class RecordStore {
    static synchronized JSONArray read(Context context) {
        try { return filtered(context,new JSONArray(context.getSharedPreferences("shiying",0).getString("downloads","[]"))); }
        catch (Exception e) { return new JSONArray(); }
    }
    static synchronized void save(Context context,JSONArray records) {
        context.getSharedPreferences("shiying",0).edit().putString("downloads",filtered(context,records).toString()).apply();
    }
    static synchronized void remove(Context context,long id) {
        context.getSharedPreferences("gallery",0).edit().putBoolean("removed_"+id,true).commit();
        context.getSharedPreferences("shiying",0).edit().putString("downloads",read(context).toString()).commit();
    }
    private static JSONArray filtered(Context context,JSONArray records) {
        SharedPreferences deleted=context.getSharedPreferences("gallery",0); JSONArray result=new JSONArray();
        for (int i=0;i<records.length();i++) {
            JSONObject item=records.optJSONObject(i);
            if (item!=null&&!deleted.getBoolean("removed_"+item.optLong("id"),false)) result.put(CompoundDownloads.decorate(context,item));
        }
        return result;
    }
}
