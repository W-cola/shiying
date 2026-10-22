"""The same verified SenseVoice/Silero model pack used by the Android app."""
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

from .douyin import check_cancel
from .models import AppError, Cancelled


def assets():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "speech"


class SpeechModels:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / "speech-model"
        self.manifest = json.loads((assets()/"model.json").read_text(encoding="utf-8"))
        self.files = self.manifest["files"]

    def ready(self):
        return all((self.root/f["name"]).is_file() and (self.root/f["name"]).stat().st_size == f["bytes"] for f in self.files)

    @staticmethod
    def verify(path, item, cancel):
        if not path.is_file() or path.stat().st_size != item["bytes"]:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(4*1024*1024):
                check_cancel(cancel)
                digest.update(chunk)
        return digest.hexdigest() == item["sha256"]

    def validate(self, cancel):
        if not all(self.verify(self.root/f["name"], f, cancel) for f in self.files):
            raise AppError("离线识别包尚未就绪或校验失败，请先下载或导入识别包。")

    def install(self, cancel, progress=lambda p: None):
        self.root.mkdir(parents=True, exist_ok=True)
        total = sum(f["bytes"] for f in self.files)
        complete = 0
        for item in self.files:
            target = self.root/item["name"]
            if self.verify(target, item, cancel):
                complete += item["bytes"]
                continue
            bundled = assets()/item["name"]
            if bundled.is_file() and self.verify(bundled, item, cancel):
                shutil.copy2(bundled, target)
            else:
                self.download(item, cancel, lambda n: progress({"done": complete+n, "total": total, "stage": "下载识别包"}))
            if not self.verify(target, item, cancel):
                raise AppError("识别包校验失败，未启用未验证的模型。")
            complete += item["bytes"]
            progress({"done": complete, "total": total, "stage": "校验识别包"})

    def download(self, item, cancel, progress):
        target = self.root/item["name"]
        partial = target.with_suffix(target.suffix+".part")
        failures = 0
        for url in [*(item.get("urls") or []), item["url"]]:
            check_cancel(cancel)
            offset = partial.stat().st_size if partial.exists() else 0
            if offset == item["bytes"] and self.verify(partial, item, cancel):
                partial.replace(target)
                return
            if offset >= item["bytes"]:
                partial.unlink(missing_ok=True)
                offset = 0
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                with requests.get(url, headers=headers, stream=True, timeout=(8, 12)) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise AppError("识别包续传响应不一致，请重试。")
                    else:
                        offset = 0
                    with partial.open("ab" if offset else "wb") as output:
                        for chunk in response.iter_content(256*1024):
                            check_cancel(cancel)
                            output.write(chunk)
                            offset += len(chunk)
                            if offset > item["bytes"]:
                                raise AppError("识别包文件大小不符，已停止下载。")
                            progress(offset)
                if self.verify(partial, item, cancel):
                    partial.replace(target)
                    return
                partial.unlink(missing_ok=True)
                failures += 1
            except Cancelled:
                raise
            except (requests.RequestException, AppError):
                failures += 1
        raise AppError(f"识别包下载未完成（已尝试 {failures} 个来源）。可以继续下载，或导入离线识别包。")

    def import_zip(self, archive, cancel, progress=lambda p: None):
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="import-", dir=self.root) as work:
            stage = Path(work)
            with zipfile.ZipFile(archive) as bundle:
                allowed = {f["name"] for f in self.files}
                names = bundle.namelist()
                if len(names) != len(set(names)) or not allowed.issubset(names) or any(n not in allowed | {"speech-model.json"} for n in names):
                    raise AppError("识别包不完整或包含额外路径，请选择原始离线 ZIP。")
                complete = 0
                total = sum(f["bytes"] for f in self.files)
                for item in self.files:
                    if bundle.getinfo(item["name"]).file_size != item["bytes"]:
                        raise AppError("识别包文件大小不符。")
                    with bundle.open(item["name"]) as source, (stage/item["name"]).open("wb") as output:
                        while chunk := source.read(256*1024):
                            check_cancel(cancel)
                            output.write(chunk)
                            complete += len(chunk)
                            progress({"done": complete, "total": total, "stage": "导入识别包"})
                    if not self.verify(stage/item["name"], item, cancel):
                        raise AppError("识别包校验失败，原有模型未改动。")
            for item in self.files:
                (stage/item["name"]).replace(self.root/item["name"])
