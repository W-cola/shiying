"""Reject explicitly watermarked renditions; never edit or guess signed URLs."""
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .models import AppError


def marked_metadata(value):
    if not isinstance(value, dict):
        return False
    for key in ("watermark", "has_watermark", "hasWatermark", "is_watermark", "isWatermark", "with_watermark", "watermark_type"):
        flag = value.get(key)
        if flag is not None and str(flag).lower() not in ("", "0", "false", "none", "null"):
            return True
    return False


def marked_url(url):
    parts = urlsplit(url)
    path = unquote(parts.path).lower()
    if "/playwm/" in path or re.search(r"(?:[-_/]|^)watermark(?:[-_/.~]|$)", path):
        return True
    for key, value in parse_qsl(parts.query):
        key, value = key.lower(), unquote(value).lower()
        if key in ("watermark", "watermark_type", "is_watermark", "with_watermark", "logo_type"):
            if value not in ("", "0", "false", "none", "null"):
                return True
        if key in ("x-tos-process", "x-oss-process", "image_process", "imageprocess") and "watermark" in value:
            return True
    return False


def require_clean(info, fmt):
    """Defense at preview/save boundaries, including backup and compound media."""
    urls = [fmt.url, *fmt.alternatives]
    for item in fmt.assets:
        urls.extend([item.get("url", ""), *(item.get("alternatives") or [])])
        if marked_metadata(item):
            raise AppError("只有带水印的媒体源，已停止保存。请重新解析无水印版本。")
    if info.kind == "images":
        for index in fmt.image_indices or range(len(info.images)):
            asset = info.images[index]
            urls.extend([asset.url, *asset.alternatives])
    if any(marked_url(url) for url in urls if url):
        raise AppError("检测到带水印的媒体地址，已停止预览和保存。请重新解析。")
