import json
import os
import sys
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
        rows = self.read("history.json", [])
        rows.insert(0, {"title": info.title, "platform": info.platform, "url": info.source_url,
                        "path": str(path), "size": path.stat().st_size,
                        "time": datetime.now().astimezone().isoformat(timespec="seconds")})
        self.write("history.json", rows[:300])
