import json
import re
import shutil
import time
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

import requests
import yt_dlp

from .douyin import DouyinResolver, check_cancel, make_session, DESKTOP_UA
from .links import available_path, douyin_id, extract_links, is_douyin, safe_filename, stable_id
from .models import AppError, Cancelled, VideoFormat, VideoInfo


def safe_message(message) -> str:
    """Avoid putting signed media URLs or credentials in the UI/log."""
    return re.sub(r'https?://[^\s\]\)]+', lambda m: urlsplit(m.group()).hostname or "链接", str(message))[:700]


class Logger:
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self.log(safe_message(msg))

    info = debug

    def warning(self, msg):
        self.log("提示：" + safe_message(msg))

    def error(self, msg):
        self.log(safe_message(msg))


class Engine:
    def __init__(self, data_dir: Path, log=lambda s: None, progress=lambda d: None, cancel=None):
        self.data_dir, self.log, self.progress = data_dir, log, progress
        self.cancel = cancel or Event()

    def resolve(self, text: str, interactive=False) -> VideoInfo:
        links = extract_links(text)
        if len(links) != 1:
            raise AppError("请一次解析一个视频链接，下载完成后再添加下一个。")
        url = links[0]
        check_cancel(self.cancel)
        if is_douyin(url):
            resolver = DouyinResolver(self.data_dir, self.log, self.cancel)
            if interactive:
                return resolver.browser(url, target=douyin_id(url), interactive=True)
            canonical, target = url, douyin_id(url)
            try:
                canonical, target, info = resolver.resolve_share(url)
                if info:
                    self.log("已从分享页读取到目标视频。")
                    return info
            except requests.RequestException as error:
                self.log("分享页请求失败，正在尝试浏览器。" + safe_message(error))
            try:
                return resolver.browser(url, canonical, target)
            except Cancelled:
                raise
            except AppError as error:
                self.log(str(error))
                if target:
                    try:
                        return self._ydl_resolve(canonical, url)
                    except Exception:
                        pass
                raise error
        if interactive:
            raise AppError("浏览器辅助解析目前用于抖音链接。其他网站请使用「解析视频」。")
        return self._ydl_resolve(url, url)

    def _ydl_options(self):
        return {"quiet": True, "no_warnings": False, "logger": Logger(self.log),
                "noplaylist": True, "socket_timeout": 15, "retries": 2,
                "extractor_retries": 1, "nocheckcertificate": False}

    def _ydl_resolve(self, url: str, source: str) -> VideoInfo:
        self.log("正在读取视频信息…")
        try:
            with yt_dlp.YoutubeDL(self._ydl_options()) as ydl:
                raw = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as error:
            check_cancel(self.cancel)
            raise AppError("无法解析此视频。请检查网络、链接及访问权限。\n" + safe_message(error)) from error
        check_cancel(self.cancel)
        if not raw or raw.get("_type") in ("playlist", "multi_video") or raw.get("is_live"):
            raise AppError("请提供单个录播视频的链接；暂不支持合集、直播或图集。")
        formats = []
        # Offer only complete AV files; never silently download video without audio.
        for f in reversed(raw.get("formats") or [raw]):
            if f.get("has_drm") or f.get("vcodec") == "none" or f.get("acodec") == "none" or not f.get("url"):
                continue
            height = f.get("height") or 0
            label = f"{f.get('width')}×{height}" if height and f.get("width") else f.get("format_note") or "可用画质"
            ext = f.get("ext") or "mp4"
            formats.append(VideoFormat(str(f.get("format_id") or "direct"), f"{label} · {ext.upper()}", f["url"], ext,
                                       height, f.get("width") or 0, f.get("filesize") or f.get("filesize_approx") or 0))
        if shutil.which("ffmpeg"):
            formats.insert(0, VideoFormat("best_merged", "最佳画质 · 自动合并音视频", ext="mp4"))
        if not formats:
            raise AppError("未找到包含声音的可下载视频。若网站分开提供音视频，请安装 FFmpeg 后重试；受保护的视频不支持下载。")
        return VideoInfo(source, raw.get("webpage_url") or url, str(raw.get("id") or stable_id(url)),
                         raw.get("title") or "视频", raw.get("uploader") or raw.get("channel") or "",
                         raw.get("duration") or 0, raw.get("thumbnail") or "",
                         "抖音" if is_douyin(source) else raw.get("extractor_key") or "网页视频", "yt-dlp", formats, raw)

    def download(self, info: VideoInfo, fmt: VideoFormat, folder: Path) -> Path:
        check_cancel(self.cancel)
        folder = folder.expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        stem = safe_filename(info.title, info.video_id)
        if info.engine == "yt-dlp":
            return self._ydl_download(info, fmt, folder, stem)
        if ".m3u8" in urlsplit(fmt.url).path.lower():
            return self._ydl_download(info, fmt, folder, stem, direct_manifest=True)
        errors = []
        for url in [fmt.url, *fmt.alternatives]:
            for attempt in range(3):
                check_cancel(self.cancel)
                try:
                    return self._stream(url, fmt, folder, stem)
                except Cancelled:
                    raise
                except (requests.RequestException, AppError) as error:
                    errors.append(safe_message(error))
                    if isinstance(error, AppError):
                        break
                    self.log(f"网络中断，准备续传（{attempt + 1}/3）…")
        raise AppError("下载未完成，已保留续传文件。可重新解析以刷新播放地址，或使用浏览器辅助解析。\n" + errors[-1])

    def _stream(self, url: str, fmt: VideoFormat, folder: Path, stem: str) -> Path:
        # Each source/quality gets its own partial; don't mix different renditions.
        tag = stable_id(fmt.key + ":" + url)
        partial = folder / f"{stem}.{tag}.part"
        metadata = partial.with_suffix(".part.json")
        meta = {}
        if metadata.exists():
            try:
                meta = json.loads(metadata.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        offset = partial.stat().st_size if partial.exists() and meta.get("url") == url else 0
        headers = {"User-Agent": DESKTOP_UA, **fmt.headers, "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            if meta.get("validator"):
                headers["If-Range"] = meta["validator"]
            self.log(f"正在续传，已保存 {offset // 1024} KB…")
        with make_session(self.data_dir / "browser-state.json") as session:
            with session.get(url, headers=headers, stream=True, timeout=(12, 18)) as response:
                if response.status_code == 416:
                    partial.unlink(missing_ok=True)
                    metadata.unlink(missing_ok=True)
                    raise requests.RequestException("服务器拒绝旧的续传位置，下一次将重新下载。")
                response.raise_for_status()
                mime = response.headers.get("Content-Type", "").lower()
                if any(t in mime for t in ("text/html", "application/json", "text/plain")):
                    raise AppError("服务器返回了网页或错误信息，未将其保存为视频。请重新解析。")
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                if encoding != "identity":
                    raise AppError("服务器返回了压缩的媒体流，无法安全续传。请换一个画质重试。")
                if response.status_code == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", response.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != offset:
                        raise AppError("服务器的续传响应不一致，已停止下载以避免损坏文件。")
                    total = int(match[3]) if match[3] != "*" else 0
                else:
                    offset = 0  # A server ignoring Range requires a clean replacement.
                    total = int(response.headers.get("Content-Length") or 0)
                validator = response.headers.get("ETag") or response.headers.get("Last-Modified") or ""
                metadata.write_text(json.dumps({"url": url, "validator": validator}), encoding="utf-8")
                done, started, last_emit = offset, time.monotonic(), 0
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in response.iter_content(chunk_size=128 * 1024):
                        check_cancel(self.cancel)
                        if not chunk:
                            continue
                        if done == 0 and chunk.lstrip()[:1] in (b"<", b"{"):
                            raise AppError("收到的内容不是视频，下载已停止。")
                        output.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if now - last_emit > .15:
                            speed = (done - offset) / max(now - started, .01)
                            self.progress({"done": done, "total": total, "speed": speed,
                                           "eta": (total - done) / speed if total and speed else 0})
                            last_emit = now
                check_cancel(self.cancel)
                if not done or (total and done != total):
                    raise requests.RequestException("文件长度与服务器声明不一致。")
                target = available_path(folder, stem, fmt.ext)
                partial.rename(target)
                metadata.unlink(missing_ok=True)
                self.progress({"done": done, "total": done, "speed": 0, "eta": 0})
                self.log("视频已完整保存。")
                return target

    def _ydl_download(self, info, fmt, folder, stem, direct_manifest=False):
        target = available_path(folder, stem, fmt.ext)
        final_paths = []

        def hook(d):
            check_cancel(self.cancel)
            if d.get("status") == "downloading":
                self.progress({"done": d.get("downloaded_bytes") or 0,
                               "total": d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                               "speed": d.get("speed") or 0, "eta": d.get("eta") or 0})
            elif d.get("status") == "finished":
                self.log("下载完成，正在检查并整理文件…")

        opts = self._ydl_options()
        opts.update({"outtmpl": str(target.with_suffix(".%(ext)s")), "windowsfilenames": True,
                     "format": "bv*+ba/b" if fmt.key == "best_merged" else fmt.key,
                     "merge_output_format": "mp4", "continuedl": True,
                     "progress_hooks": [hook],
                     "post_hooks": [lambda p: final_paths.append(p)]})
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                if direct_manifest:
                    raw = {"id": info.video_id, "title": info.title, "url": fmt.url,
                           "ext": fmt.ext, "protocol": "m3u8_native", "http_headers": fmt.headers}
                else:
                    # Avoid a second extraction changing the available format IDs.
                    raw = dict(info.raw)
                result = ydl.process_ie_result(raw, download=True)
                paths = [Path(p) for p in final_paths]
                if result:
                    paths.extend(Path(p) for p in (result.get("filepath"), result.get("_filename")) if p)
                paths.append(target)
                for path in paths:
                    if path.is_file() and path.stat().st_size > 0 and path.suffix != ".part":
                        return path.resolve()
        except Cancelled:
            raise
        except yt_dlp.utils.DownloadError as error:
            check_cancel(self.cancel)
            raise AppError("下载失败。重新解析可以刷新过期的视频地址。\n" + safe_message(error)) from error
        raise AppError("下载器未返回完整的文件，请查看运行记录。")
