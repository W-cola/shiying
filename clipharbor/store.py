import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path


def app_root() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


class Store:
    """Portable application state; no browsing data from the user's regular browser."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("CLIPHARBOR_DATA", str(app_root() / "data")))
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = self.read("settings.json", {"download_dir": str(app_root() / "downloads")})

    def read(self, name, default):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def write(self, name, data):
        path = self.root / name
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def save_settings(self):
        self.write("settings.json", self.settings)

    def add_history(self, info, path: Path):
        from .models import SavedMedia
        result = path if isinstance(path, SavedMedia) else SavedMedia(Path(path), [Path(path)], "video")
        files = [Path(p).resolve() for p in result.files]
        rows = self.read("history.json", [])
        rows.insert(0, {"id": uuid.uuid4().hex, "title": info.title, "author": info.author,
                        "platform": info.platform, "url": info.source_url, "description": info.description,
                        "kind": result.kind, "files": [str(p) for p in files],
                        "path": str(Path(result.path).resolve()), "size": sum(p.stat().st_size for p in files),
                        "time": datetime.now().astimezone().isoformat(timespec="seconds")})
        if info.raw.get("library_origin_path"):
            rows[0]["origin_path"] = info.raw["library_origin_path"]
        self.write("history.json", rows)

    def records(self, kind="", search=""):
        rows = self.read("history.json", [])
        if not isinstance(rows, list):
            return []
        search = search.casefold().strip()
        return [x for x in rows if isinstance(x, dict) and x.get("path") and
                (not kind or x.get("kind", "video") == kind) and
                (not search or search in (x.get("title", "") + " " + x.get("author", "")).casefold())]

    def delete_record(self, record, delete_files=True):
        """Delete precisely this batch; leave other batches and unrelated files alone."""
        rows = self.read("history.json", [])
        match = next((x for x in rows if x == record), None)
        if match is None:
            return
        if delete_files:
            primary = Path(match["path"]).resolve()
            for name in match.get("files") or [match["path"]]:
                path = Path(name).resolve()
                if match.get("kind") == "images":
                    if path.parent != primary or path.is_symlink():
                        raise OSError("图文文件不属于当前批次，已停止删除。")
                elif path != primary:
                    raise OSError("文件不属于当前记录，已停止删除。")
                path.unlink(missing_ok=True)
            if match.get("kind") == "images" and primary.is_dir() and not any(primary.iterdir()):
                primary.rmdir()
        rows.remove(match)
        self.write("history.json", rows)
