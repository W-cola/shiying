import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .models import AppError

URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。！？；、（）【】]+", re.I)


def extract_links(text: str) -> list[str]:
    links = []
    for match in URL_PATTERN.finditer(text):
        url = match.group().rstrip(".,;!?)]}）")
        parts = urlsplit(url)
        if parts.username or parts.password or not parts.hostname:
            raise AppError("链接格式不正确，请粘贴完整的 http 或 https 分享链接。")
        url = urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))
        if url not in links:
            links.append(url)
    if not links:
        raise AppError("没有找到链接。可以粘贴抖音整段分享文字，或完整的视频网页地址。")
    return links


def is_douyin(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in ("douyin.com", "iesdouyin.com"))


def douyin_id(url: str) -> str:
    parts = urlsplit(url)
    match = re.search(r"/(?:share/)?(?:video|note|slides)/(\d+)", parts.path)
    if match:
        return match.group(1)
    for key in ("modal_id", "aweme_id", "item_id"):
        value = parse_qs(parts.query).get(key, [""])[0]
        if value.isdigit():
            return value
    return ""


def safe_filename(title: str, video_id: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
    clean = re.sub(r"\s+", " ", clean).strip(" .")[:70].rstrip(" .") or "视频"
    # Windows reserves these names even when an extension is present.
    if clean.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        clean = "_" + clean
    token = re.sub(r"[^a-zA-Z0-9_-]", "", video_id)[:40]
    return f"{clean} [{token or 'video'}]"


def stable_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def available_path(folder: Path, stem: str, ext: str) -> Path:
    ext = ext if re.fullmatch(r"[a-zA-Z0-9]{1,8}", ext) else "mp4"
    candidate = folder / f"{stem}.{ext}"
    count = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({count}).{ext}"
        count += 1
    return candidate
