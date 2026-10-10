package cn.shiying.mobile;

import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Continues media publication when the application's screen is closed. */
public final class DownloadCompleteReceiver extends BroadcastReceiver {
    private static final java.util.concurrent.ExecutorService worker=java.util.concurrent.Executors.newSingleThreadExecutor();
    @Override public void onReceive(Context context,Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) { CompoundDownloads.recover(context); return; }
        if (!DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction())) return;
        long id=intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID,-1);
        if (id<0) return;
        PendingResult result=goAsync();
        worker.execute(()-> {
            if (CompoundDownloads.childComplete(context,id)) result.finish(); else MediaPublisher.publish(context,id,result::finish);
        });
    }
}
