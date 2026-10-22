"""Independent preview tasks: never occupy the save/resolve worker or block Qt."""
import shutil
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget

from .douyin import make_session, check_cancel
from .engine import Engine
from .player import PlayerWidget
from .preview import PreviewRelay, can_stream
from .watermark import require_clean, marked_url


class PreviewTask(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, data_dir, info, fmt, image_url="", parent=None):
        super().__init__(parent)
        self.data_dir, self.info, self.fmt, self.image_url = data_dir, info, fmt, image_url
        self.cancel = Event()

    def run(self):
        try:
            if self.image_url:
                with make_session(self.data_dir / "browser-state.json") as session:
                    headers = {"Referer": self.info.page_url, **self.fmt.headers}
                    with session.get(self.image_url, headers=headers, stream=True, timeout=(5, 6)) as response:
                        response.raise_for_status()
                        if marked_url(response.url):
                            raise ValueError("图片跳转到了带水印版本")
                        data = bytearray()
                        for chunk in response.iter_content(64*1024):
                            check_cancel(self.cancel)
                            data.extend(chunk)
                            if len(data) > 12*1024*1024:
                                raise ValueError("图片过大")
                        image = QImage.fromData(bytes(data))
                        if image.isNull():
                            raise ValueError("图片格式暂不支持")
                        self.result.emit(image)
            else:
                self.result.emit(Engine(self.data_dir, cancel=self.cancel).prepare_preview(self.info, self.fmt))
        except Exception:
            if not self.cancel.is_set():
                self.failed.emit("画面暂未加载，点击重试；仍可直接保存。")


class PreviewPane(QWidget):
    stopped = Signal()
    ready = Signal()
    notice = Signal(str)

    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.generation = 0
        self.tasks = []
        self.cache_dir = None
        self.closing = False
        self.info = None
        self.image_index = 0
        self.image = QImage()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.stack = QStackedWidget()
        self.media = PlayerWidget()
        self.media.ready.connect(self.ready)
        self.media.failed.connect(self.stream_failed)
        self.stack.addWidget(self.media)
        album = QWidget()
        ab = QVBoxLayout(album)
        ab.setContentsMargins(0, 0, 0, 0)
        self.image_label = QLabel("正在加载图片…")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(260, 220)
        self.image_label.setStyleSheet("background:#10251b;color:#c5d6ca;border-radius:14px;")
        ab.addWidget(self.image_label, 1)
        row = QHBoxLayout()
        self.previous = QPushButton("←")
        self.next = QPushButton("→")
        self.count = QLabel()
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for button in (self.previous, self.next):
            button.setFixedWidth(42)
        row.addStretch()
        row.addWidget(self.previous)
        row.addWidget(self.count)
        row.addWidget(self.next)
        row.addStretch()
        ab.addLayout(row)
        self.previous.clicked.connect(lambda: self.move_image(-1))
        self.next.clicked.connect(lambda: self.move_image(1))
        self.stack.addWidget(album)
        box.addWidget(self.stack, 1)

    def clear(self):
        self.generation += 1
        for task in self.tasks:
            task.cancel.set()
        if self.media.fullscreen_window:
            self.media.exit_fullscreen()
        self.media.clear()
        if self.cache_dir:
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            self.cache_dir = None
        self.info = None
        self.fallback_started = False
        self.image = QImage()
        self.image_label.clear()
        self.stack.setCurrentIndex(0)

    def set_info(self, info, fmt):
        self.clear()
        try:
            require_clean(info, fmt)
        except Exception as error:
            self.notice.emit(str(error))
            return
        self.info, self.fmt = info, fmt
        if info.kind == "images":
            self.stack.setCurrentIndex(1)
            self.image_index = fmt.image_indices[0] if fmt.image_indices else 0
            self.load_image()
        else:
            if can_stream(info, fmt):
                relay = PreviewRelay(self.data_dir, fmt)
                self.media.set_source(QUrl(relay.url), relay=relay, duration=info.duration)
            else:
                self.media.surface.placeholder = "正在准备预览，仍可操作保存设置…"
                self.media.surface.update()
                self.task(PreviewTask(self.data_dir, info, fmt), self.local_ready)
            if info.thumbnail:
                self.task(PreviewTask(self.data_dir, info, fmt, info.thumbnail), self.media.set_poster, quiet=True)

    def task(self, task, callback, quiet=False):
        generation = self.generation
        self.tasks.append(task)

        def result(value):
            if generation != self.generation or self.closing:
                if hasattr(value, "cache_dir") and value.cache_dir:
                    shutil.rmtree(value.cache_dir, ignore_errors=True)
                return
            callback(value)

        task.result.connect(result)
        if not quiet:
            task.failed.connect(lambda message: self.notice.emit(message) if generation == self.generation else None)

        def finished():
            self.tasks.remove(task)
            task.deleteLater()
            if self.closing and not self.tasks:
                self.stopped.emit()

        task.finished.connect(finished)
        task.start()

    def local_ready(self, result):
        self.cache_dir = result.cache_dir
        self.media.set_source(QUrl.fromLocalFile(str(Path(result.path).resolve())), duration=self.info.duration)

    def stream_failed(self, message):
        if self.info and can_stream(self.info, self.fmt) and not self.fallback_started and not self.closing:
            self.fallback_started = True
            self.media.show_hint("正在切换兼容预览…", 0)
            self.task(PreviewTask(self.data_dir, self.info, self.fmt), self.local_ready)
        else:
            self.notice.emit(message)

    def move_image(self, delta):
        if self.info:
            self.image_index = max(0, min(len(self.info.images)-1, self.image_index+delta))
            self.load_image()

    def load_image(self):
        self.generation += 1
        for task in self.tasks:
            task.cancel.set()
        self.image = QImage()
        self.image_label.setText("正在加载图片…")
        self.count.setText(f"{self.image_index+1} / {len(self.info.images)}")
        self.previous.setEnabled(self.image_index > 0)
        self.next.setEnabled(self.image_index < len(self.info.images)-1)
        self.task(PreviewTask(self.data_dir, self.info, self.fmt, self.info.images[self.image_index].url), self.image_ready)

    def image_ready(self, image):
        self.image = image
        self.paint_image()
        self.ready.emit()

    def paint_image(self):
        if not self.image.isNull():
            self.image_label.setPixmap(QPixmap.fromImage(self.image).scaled(self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.paint_image()

    def shutdown(self):
        self.closing = True
        self.clear()
        if not self.tasks:
            self.media.dispose()
            return True
        return False
