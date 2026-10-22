from dataclasses import dataclass, field


class AppError(Exception):
    """An actionable, user-facing failure."""


class Cancelled(AppError):
    pass


@dataclass
class VideoFormat:
    key: str
    label: str
    url: str = ""
    ext: str = "mp4"
    height: int = 0
    width: int = 0
    size: int = 0
    headers: dict = field(default_factory=dict, repr=False)
    alternatives: list[str] = field(default_factory=list, repr=False)
    mode: str = "direct"
    assets: list = field(default_factory=list, repr=False)
    image_indices: list[int] = field(default_factory=list)
    decode_key: str = field(default="", repr=False)


@dataclass
class ImageAsset:
    url: str
    width: int = 0
    height: int = 0
    alternatives: list[str] = field(default_factory=list, repr=False)


@dataclass
class VideoInfo:
    source_url: str
    page_url: str
    video_id: str
    title: str
    author: str = ""
    duration: float = 0
    thumbnail: str = ""
    platform: str = ""
    engine: str = "direct"
    formats: list[VideoFormat] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)
    kind: str = "video"
    description: str = ""
    images: list[ImageAsset] = field(default_factory=list)


@dataclass
class SavedMedia:
    path: object
    files: list
    kind: str
    temporary: bool = False
    cache_dir: object = None


def human_size(size: float) -> str:
    if not size:
        return "大小未知"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def human_duration(seconds: float) -> str:
    if not seconds:
        return "时长未知"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def format_label(fmt):
    """Use human readable quality names instead of platform codec/gear IDs."""
    if fmt.width and fmt.height:
        edge = min(fmt.width, fmt.height)
        name = "4K" if edge >= 2160 else "2K" if edge >= 1440 else f"{edge}P"
        dimensions = f"{fmt.width} × {fmt.height}"
        return " · ".join([name, dimensions] + ([human_size(fmt.size)] if fmt.size else []))
    return fmt.label + (" · " + human_size(fmt.size) if fmt.size else "")
