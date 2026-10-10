package cn.shiying.mobile;

import android.app.job.JobParameters;
import android.app.job.JobService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ConcurrentHashMap;

/** JobScheduler can finish downloaded media after the screen or app process closes. */
public final class MediaAssemblyJob extends JobService {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final ConcurrentHashMap<Integer,Future<?>> running=new ConcurrentHashMap<>();
    @Override public boolean onStartJob(JobParameters params) {
        long id=params.getExtras().getLong("recordId");
        String state=CompoundDownloads.job(this,id).optString("state"); if (state.equals("done")||state.equals("cancelled")||state.equals("failed")) return false;
        Future<?> work=worker.submit(()-> {
            boolean retry=false;
            try { MediaAssembler.assemble(this,id); }
            catch (InterruptedException e) { retry=!CompoundDownloads.cancelled(this,id); }
            catch (Exception e) {
                if (!CompoundDownloads.cancelled(this,id)) { CompoundDownloads.update(this,id,"error",CompoundDownloads.job(this,id).optBoolean("audio")?(e.getMessage()==null?"音频提取失败，请重新解析并重试。":e.getMessage()):"当前媒体无法合并，可重新解析并选择完整 MP4。"); CompoundDownloads.update(this,id,"state","failed"); CompoundDownloads.cleanupParts(this,CompoundDownloads.job(this,id)); }
            } finally { running.remove(params.getJobId()); jobFinished(params,retry); }
        });
        running.put(params.getJobId(),work); return true;
    }
    @Override public boolean onStopJob(JobParameters params) { Future<?> work=running.remove(params.getJobId()); if (work!=null) work.cancel(true); return !CompoundDownloads.cancelled(this,params.getExtras().getLong("recordId")); }
    @Override public void onDestroy() { worker.shutdownNow(); super.onDestroy(); }
}
