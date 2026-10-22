"""Bounded preview caches, grouped pictures, FFmpeg assembly and audio export."""
import dataclasses
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .douyin import check_cancel
from .links import available_path, safe_filename
from .models import AppError, Cancelled, SavedMedia, VideoFormat

LIMIT = 1024**3


def ffmpeg():
    # Portable builds carry imageio-ffmpeg's executable; do not rely on PATH.
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args, cancel):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)],
                                   stdout=subprocess.DEVNULL, stderr=errors,
                                   stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                check_cancel(cancel)
                time.sleep(.1)
            check_cancel(cancel)
            if process.returncode:
                # URLs and decoder internals are not useful in the product UI.
                raise AppError("媒体处理未完成。文件可能没有音轨、编码不受支持或媒体内容不完整。")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def image_extension(path):
    with Path(path).open("rb") as f:
        header = f.read(64)
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    if header[4:8] == b"ftyp" and any(brand in header[8:] for brand in (b"avif", b"avis", b"heic", b"heix", b"mif1")):
        return "avif" if b"avif" in header[8:] else "heic"
    raise AppError("服务器没有返回有效图片，未保存网页或封面占位内容。")


def cache_directory(engine):
    root = engine.data_dir / "preview-cache"
    root.mkdir(parents=True, exist_ok=True)
    for path in root.glob("preview-*"):
        if path.is_dir() and not path.is_symlink() and time.time() - path.stat().st_mtime > 86400:
            shutil.rmtree(path, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix="preview-", dir=root))


def save_album(engine, info, fmt, folder):
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    indices = fmt.image_indices or list(range(len(info.images)))
    if not indices or any(i < 0 or i >= len(info.images) for i in indices):
        raise AppError("图片选择已失效，请重新解析。")
    staging = Path(tempfile.mkdtemp(prefix=".shiying-album-", dir=folder))
    stem = safe_filename(info.title, info.video_id)
    try:
        files = []
        for n, i in enumerate(indices):
            check_cancel(engine.cancel)
            engine.log(f"正在保存第 {n+1}/{len(indices)} 张图片…")
            image = info.images[i]
            image_fmt = VideoFormat(f"image-{i}", f"第 {i+1} 张", image.url, "jpg", headers=fmt.headers,
                                    alternatives=image.alternatives)
            picture_info = dataclasses.replace(info, kind="video", engine="direct", title=f"{i+1:03}", video_id=str(i+1))
            path = engine.download(picture_info, image_fmt, staging)
            extension = image_extension(path)
            target = staging / f"{i+1:03}.{extension}"
            path.rename(target)
            files.append(target.name)
            if getattr(engine, "limit_bytes", 0) and sum(x.stat().st_size for x in staging.iterdir() if x.is_file()) > engine.limit_bytes:
                raise AppError("图文预览超过 1 GiB 上限，请直接保存。")
        source = urlsplit(info.page_url)
        text = f"{info.title}\n\n作者：{info.author}\n平台：{info.platform}\n来源：{source.scheme}://{source.netloc}{source.path}\n\n{info.description}\n"
        (staging / "正文.txt").write_text(text, encoding="utf-8")
        files.append("正文.txt")
        check_cancel(engine.cancel)
        target = folder / stem
        index = 1
        while target.exists():
            target = folder / f"{stem} ({index})"
            index += 1
        staging.rename(target)
        return SavedMedia(target, [target / x for x in files], "images")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def assemble(engine, info, fmt, folder):
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    work = cache_directory(engine)
    try:
        inputs = []
        for n, asset in enumerate(fmt.assets or [{"url": fmt.url, "alternatives": fmt.alternatives}]):
            check_cancel(engine.cancel)
            part = VideoFormat(f"asset-{n}", "媒体片段", asset["url"], headers=fmt.headers,
                               alternatives=asset.get("alternatives") or [])
            part_info = dataclasses.replace(info, kind="video", engine="direct", title=f"asset-{n}")
            inputs.append(engine.download(part_info, part, work))
            if getattr(engine, "limit_bytes", 0) and sum(p.stat().st_size for p in inputs) > engine.limit_bytes:
                raise AppError("预览媒体超过 1 GiB 上限，请直接保存。")
        if fmt.decode_key:
            from .channels_codec import ChannelsCodec
            codec = ChannelsCodec(fmt.decode_key)
            with inputs[0].open("r+b") as output:
                prefix = output.read(131072)
                output.seek(0)
                output.write(codec.apply(prefix))
        output = work / "assembled.mp4"
        engine.log("正在整理完整音视频…")
        if fmt.mode == "dash":
            args = ["-i", inputs[0], "-i", inputs[1], "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", output]
        elif fmt.mode == "concat":
            listing = work / "segments.txt"
            # Generated basenames only; never interpolate a remote filename into a concat script.
            listing.write_text("\n".join("file '" + path.name + "'" for path in inputs), encoding="utf-8")
            args = ["-f", "concat", "-safe", "1", "-i", listing, "-c", "copy", "-movflags", "+faststart", output]
        else:
            args = ["-i", inputs[0], "-c", "copy", "-movflags", "+faststart", output]
        run_ffmpeg(args, engine.cancel)
        target = available_path(folder, safe_filename(info.title, info.video_id), "mp4")
        shutil.move(str(output), str(target))
        return target
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prepare_preview(engine, info, fmt):
    work = cache_directory(engine)
    previous_limit = getattr(engine, "limit_bytes", 0)
    engine.limit_bytes = LIMIT
    try:
        engine.log("正在准备应用内预览，不会添加下载记录…")
        result = engine.download(info, fmt, work)
        files = result.files if isinstance(result, SavedMedia) else [result]
        path = result.path if isinstance(result, SavedMedia) else result
        if sum(p.stat().st_size for p in files) > LIMIT:
            raise AppError("预览媒体超过 1 GiB 上限，请直接保存。")
        return SavedMedia(path, files, info.kind, True, work)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        engine.limit_bytes = previous_limit


def extract_audio(engine, info, fmt, folder, local_path=None):
    if info.kind == "images":
        raise AppError("图文没有可提取的原声音轨。")
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    work = cache_directory(engine)
    previous_limit = getattr(engine, "limit_bytes", 0)
    engine.limit_bytes = LIMIT
    try:
        source = Path(local_path) if local_path else None
        if source is None:
            if fmt.mode == "dash":
                sound = next((x for x in fmt.assets if x.get("kind") == "audio"), None)
                if not sound:
                    raise AppError("当前来源没有音轨。")
                source = engine.download(dataclasses.replace(info, engine="direct"),
                    VideoFormat("audio", "独立声音流", sound["url"], "m4a", headers=fmt.headers, alternatives=sound.get("alternatives") or []), work)
            else:
                source = engine.download(info, fmt, work)
        if not source.is_file():
            raise AppError("原视频已移动或删除，请重新下载。")
        output = work / "audio.m4a"
        engine.log("正在提取原声，AAC 优先直接封装为 M4A…")
        try:
            run_ffmpeg(["-i", source, "-map", "0:a:0", "-vn", "-c:a", "copy", "-movflags", "+faststart", output], engine.cancel)
        except AppError:
            check_cancel(engine.cancel)
            run_ffmpeg(["-i", source, "-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output], engine.cancel)
        if not output.is_file() or output.stat().st_size < 128:
            raise AppError("没有生成有效的音频文件。")
        target = available_path(folder, safe_filename(info.title + "_原声", info.video_id), "m4a")
        shutil.move(str(output), str(target))
        return SavedMedia(target, [target], "audio")
    finally:
        engine.limit_bytes = previous_limit
        shutil.rmtree(work, ignore_errors=True)
