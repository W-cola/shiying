"""In-app video/audio and album viewers; no external player is launched."""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QRectF
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QShortcut, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTextEdit, QVBoxLayout, QWidget)
from .widgets import ComboBox as QComboBox


def time_text(ms):
    seconds = max(0, int(ms / 1000))
    return f"{seconds // 60}:{seconds % 60:02}"


class VideoSurface(QWidget):
    tapped = Signal()
    toggle = Signal()
    seek = Signal(float)
    volume = Signal(float)
    moved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.rotation = 0
        self.brightness = 0
        self.down = None
        self.dragged = False
        self.setMinimumSize(240, 150)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#081710;")

    def frame(self, value):
        image = value.toImage()
        if not image.isNull():
            self.image = image
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#081710"))
        if self.image.isNull():
            painter.setPen(QColor("#d6eadc"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "拾影 · 原声播放" if self.property("audio") else "正在准备画面…")
            return
        image = self.image.transformed(QTransform().rotate(self.rotation)) if self.rotation else self.image
        size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())
        painter.drawImage(target, image)
        if self.brightness:
            color = QColor("white" if self.brightness > 0 else "black")
            color.setAlphaF(abs(self.brightness))
            painter.fillRect(target, color)

    def mousePressEvent(self, event):
        self.down = event.position()
        self.dragged = False

    def mouseMoveEvent(self, event):
        self.moved.emit()
        if self.down is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        delta = event.position() - self.down
        if abs(delta.x()) + abs(delta.y()) < 12:
            return
        self.dragged = True
        if abs(delta.x()) > abs(delta.y()):
            self.seek.emit(delta.x() / max(1, self.width()))
        elif self.down.x() < self.width()/2:
            self.brightness = max(-.7, min(.7, self.brightness - delta.y()/max(1, self.height())))
            self.update()
        else:
            self.volume.emit(-delta.y()/max(1, self.height()))
        self.down = event.position()

    def mouseReleaseEvent(self, event):
        if not self.dragged:
            self.tapped.emit()
        self.down = None

    def mouseDoubleClickEvent(self, event):
        self.toggle.emit()


class PlayerDialog(QDialog):
    def __init__(self, result, title, parent=None):
        super().__init__(parent)
        self.result = result
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title + " · 拾影播放器")
        self.resize(960, 700)
        self.resume_when_active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.surface = VideoSurface()
        self.surface.setProperty("audio", result.kind == "audio")
        layout.addWidget(self.surface, 1)
        self.controls = QFrame()
        self.controls.setObjectName("playerControls")
        controls = QVBoxLayout(self.controls)
        controls.setContentsMargins(16, 12, 16, 12)
        self.message = QLabel(title)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        controls.addWidget(self.message)
        position_row = QHBoxLayout()
        self.position_label = QLabel("0:00 / 0:00")
        position_row.addWidget(self.position_label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        position_row.addWidget(self.slider, 1)
        controls.addLayout(position_row)
        row = QHBoxLayout()
        self.play_button = QPushButton("暂停")
        self.back = QPushButton("−15 秒")
        self.forward = QPushButton("+15 秒")
        self.fullscreen = QPushButton("全屏")
        self.rotate = QPushButton("旋转画面")
        self.loop = QCheckBox("循环")
        self.rate = QComboBox()
        for rate in (.5, .75, 1., 1.25, 1.5, 2.):
            self.rate.addItem(f"{rate:g}×", rate)
        self.rate.setCurrentIndex(2)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setMaximumWidth(100)
        for widget in (self.back, self.play_button, self.forward, self.rate, self.loop, QLabel("音量"), self.volume_slider, self.rotate, self.fullscreen):
            row.addWidget(widget)
        controls.addLayout(row)
        brightness = QHBoxLayout()
        brightness.addWidget(QLabel("画面亮度"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-70, 70)
        self.brightness_slider.setMaximumWidth(180)
        brightness.addWidget(self.brightness_slider)
        brightness.addWidget(QLabel("空格暂停 · ← → 跳转 · F 全屏 · Esc 返回 · 左右拖动进度，左右半屏上下拖动调亮度/音量"), 1)
        controls.addLayout(brightness)
        layout.addWidget(self.controls)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.8)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.surface.frame)
        self.player.setVideoSink(self.sink)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(lambda error, message: self.message.setText("播放未完成：" + message))
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.play_button.clicked.connect(self.toggle)
        self.back.clicked.connect(lambda: self.seek(-15000))
        self.forward.clicked.connect(lambda: self.seek(15000))
        self.rate.currentIndexChanged.connect(lambda: self.player.setPlaybackRate(self.rate.currentData()))
        self.loop.toggled.connect(lambda checked: self.player.setLoops(QMediaPlayer.Loops.Infinite if checked else QMediaPlayer.Loops.Once))
        self.volume_slider.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        self.brightness_slider.valueChanged.connect(self.change_brightness)
        self.fullscreen.clicked.connect(self.toggle_fullscreen)
        self.rotate.clicked.connect(self.rotate_picture)
        self.surface.toggle.connect(self.toggle)
        self.surface.tapped.connect(self.toggle_controls)
        self.surface.seek.connect(lambda fraction: self.seek(int(fraction * max(self.player.duration(), 60000))))
        self.surface.volume.connect(lambda fraction: self.volume_slider.setValue(self.volume_slider.value() + int(fraction * 100)))
        self.surface.moved.connect(self.reveal)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_controls)
        self.shortcuts = []
        for key, callback in (("Space", self.toggle), ("Left", lambda: self.seek(-15000)), ("Right", lambda: self.seek(15000)),
                              ("F", self.toggle_fullscreen), ("Escape", self.escape), (Qt.Key.Key_MediaTogglePlayPause, self.toggle)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        QApplication.instance().applicationStateChanged.connect(self.app_state)
        self.player.setSource(QUrl.fromLocalFile(str(Path(result.path).resolve())))
        self.player.play()

    def position_changed(self, value):
        if not self.slider.isSliderDown():
            self.slider.setValue(value)
        self.position_label.setText(time_text(value) + " / " + time_text(self.player.duration()))

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def state_changed(self, state):
        self.play_button.setText("暂停" if state == QMediaPlayer.PlaybackState.PlayingState else "播放")
        self.reveal()

    def seek(self, delta):
        self.player.setPosition(max(0, min(self.player.duration(), self.player.position()+delta)))
        self.reveal()

    def rotate_picture(self):
        self.surface.rotation = (self.surface.rotation + 90) % 360
        self.surface.update()

    def change_brightness(self, value):
        self.surface.brightness = value / 100
        self.surface.update()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen.setText("全屏")
            self.controls.show()
        else:
            self.showFullScreen()
            self.fullscreen.setText("退出全屏")
            self.controls.hide()
        self.hide_timer.stop()

    def toggle_controls(self):
        if self.isFullScreen() and self.controls.isVisible():
            self.controls.hide()
        else:
            self.reveal()

    def reveal(self):
        self.controls.show()
        if self.isFullScreen() and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.hide_timer.start(3000)

    def hide_controls(self):
        if self.isFullScreen() and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.controls.hide()

    def escape(self):
        self.toggle_fullscreen() if self.isFullScreen() else self.close()

    def app_state(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.resume_when_active = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            self.player.pause()
        elif self.resume_when_active:
            self.resume_when_active = False
            self.player.play()

    def closeEvent(self, event):
        self.hide_timer.stop()
        try:
            QApplication.instance().applicationStateChanged.disconnect(self.app_state)
        except RuntimeError:
            pass
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setVideoSink(None)
        if self.result.temporary and self.result.cache_dir:
            shutil.rmtree(self.result.cache_dir, ignore_errors=True)
        event.accept()


class GalleryCanvas(QLabel):
    swipe = Signal(int)

    def mousePressEvent(self, event):
        self.start_x = event.position().x()

    def mouseReleaseEvent(self, event):
        delta = event.position().x() - getattr(self, "start_x", event.position().x())
        if abs(delta) > 40:
            self.swipe.emit(1 if delta < 0 else -1)


class GalleryDialog(QDialog):
    def __init__(self, result, title, description="", parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QPixmap
        self.result, self.index = result, 0
        self.files = [Path(p) for p in result.files if Path(p).suffix.lower() != ".txt"]
        self.pixmap = QPixmap()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title + " · 拾影图文")
        self.resize(900, 760)
        box = QVBoxLayout(self)
        self.caption = QLabel(title)
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(True)
        box.addWidget(self.caption)
        self.canvas = GalleryCanvas()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumSize(200, 160)
        self.canvas.setStyleSheet("background:#10271d;border-radius:10px;color:white;")
        box.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        self.previous = QPushButton("← 上一张")
        self.next = QPushButton("下一张 →")
        self.count = QLabel()
        self.full = QPushButton("全屏")
        self.text_button = QPushButton("查看正文")
        for widget in (self.previous, self.count, self.next, self.text_button, self.full):
            row.addWidget(widget)
        box.addLayout(row)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(description)
        self.text.setMaximumHeight(150)
        self.text.hide()
        box.addWidget(self.text)
        self.previous.clicked.connect(lambda: self.move(-1))
        self.next.clicked.connect(lambda: self.move(1))
        self.canvas.swipe.connect(self.move)
        self.text_button.clicked.connect(lambda: self.text.setVisible(not self.text.isVisible()))
        self.full.clicked.connect(lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())
        self.shortcuts = []
        for key, callback in (("Left", lambda: self.move(-1)), ("Right", lambda: self.move(1)), ("Escape", self.escape)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.move(0)

    def escape(self):
        self.showNormal() if self.isFullScreen() else self.close()

    def move(self, delta):
        from PySide6.QtGui import QPixmap
        self.index = max(0, min(max(0, len(self.files)-1), self.index + delta))
        self.pixmap = QPixmap(str(self.files[self.index])) if self.files else QPixmap()
        self.count.setText(f"{self.index+1 if self.files else 0} / {len(self.files)}")
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index < len(self.files)-1)
        self.paint_image()

    def paint_image(self):
        if not self.pixmap.isNull():
            self.canvas.setPixmap(self.pixmap.scaled(self.canvas.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.canvas.setText("该图片编码无法在此预览，可打开保存位置查看原文件。")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.paint_image()

    def closeEvent(self, event):
        self.canvas.clear()
        if self.result.temporary and self.result.cache_dir:
            shutil.rmtree(self.result.cache_dir, ignore_errors=True)
        event.accept()
