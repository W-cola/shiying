"""In-app video/audio and album viewers; no external player is launched."""
import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QRectF, QSize, QPoint
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QShortcut, QTransform, QPainterPath, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTextEdit, QVBoxLayout, QWidget, QToolButton, QGraphicsDropShadowEffect)
from .widgets import ComboBox as QComboBox
from .icons import glyph

PLAYER_STYLE = """
QWidget#mediaPlayer { background: #0d1c16; border-radius: 14px; }
QFrame#transport { background: rgba(12, 26, 20, 235); border: 1px solid rgba(255,255,255,22); border-radius: 12px; }
QFrame#transport QLabel { color: #e0e9e3; font-size: 11px; background: transparent; }
QFrame#transport QToolButton { background: transparent; border: none; border-radius: 7px; padding: 3px; }
QFrame#transport QToolButton:hover { background: rgba(255,255,255,28); }
QFrame#transport QToolButton:pressed { background: rgba(255,255,255,45); }
QFrame#transport QSlider::groove:horizontal { height: 3px; background: #526159; border: none; border-radius: 1px; }
QFrame#transport QSlider::sub-page:horizontal { background: #b6d7be; border-radius: 1px; }
QFrame#transport QSlider::add-page:horizontal { background: #526159; border-radius: 1px; }
QFrame#transport QSlider::handle:horizontal { width: 8px; height: 8px; margin: -4px 0; border: 1px solid #e9f3eb; border-radius: 5px; background: #e9f3eb; }
QLabel#playerHint { color: #e5eee8; background: rgba(14,29,22,205); border-radius: 8px; padding: 7px 12px; font-size: 12px; }
QFrame#playbackSettings { background: #ffffff; border: 1px solid #d4e0d6; border-radius: 12px; }
"""


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
        self.paused = True
        self.placeholder = "粘贴分享链接，画面会出现在这里"
        self.setMinimumSize(240, 150)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def frame(self, value):
        image = value.toImage()
        if not image.isNull():
            self.image = image
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor("#0d1c16"))
        if self.image.isNull():
            painter.setPen(QColor("#d6eadc"))
            painter.drawText(self.rect().adjusted(22, 20, -22, -20), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             "拾影 · 原声播放" if self.property("audio") else self.placeholder)
            return
        image = self.image.transformed(QTransform().rotate(self.rotation)) if self.rotation else self.image
        size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())
        painter.drawImage(target, image)
        if self.brightness:
            color = QColor("white" if self.brightness > 0 else "black")
            color.setAlphaF(abs(self.brightness))
            painter.fillRect(target, color)
        if self.paused and not self.image.isNull():
            center = self.rect().center()
            painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
            painter.setBrush(QColor(12, 29, 21, 175))
            painter.drawEllipse(center, 28, 28)
            glyph("play", "#ffffff").paint(painter, center.x()-14, center.y()-14, 28, 28)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
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
        if event.button() == Qt.MouseButton.LeftButton and not self.dragged and self.down is not None:
            self.tapped.emit()
        self.down = None

    def mouseDoubleClickEvent(self, event):
        self.down = None
        self.toggle.emit()


class SeekSlider(QSlider):
    """Click anywhere on the timeline; dragging previews the target immediately."""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            value = self.minimum() + round((self.maximum()-self.minimum()) * event.position().x() / max(1, self.width()))
            self.setValue(max(self.minimum(), min(self.maximum(), value)))
            self.sliderMoved.emit(self.value())
        super().mousePressEvent(event)


class FullscreenWindow(QDialog):
    def reject(self):
        self.media.exit_fullscreen()

    def closeEvent(self, event):
        self.media.exit_fullscreen()
        event.accept()


class PlayerWidget(QWidget):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, parent=None, fullscreen_owner=None):
        super().__init__(parent)
        self.setObjectName("mediaPlayer")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(PLAYER_STYLE)
        self.setMinimumSize(260, 240)
        self.fullscreen_owner = fullscreen_owner
        self.fullscreen_window = None
        self.relay = None
        self.preloading = False
        self.has_source = False
        self.loaded_frame = False
        self.resume_when_active = False
        self.message = QLabel()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.surface = VideoSurface(self)
        layout.addWidget(self.surface)
        self.controls = QFrame(self.surface)
        self.controls.setObjectName("transport")
        controls = QVBoxLayout(self.controls)
        controls.setContentsMargins(12, 5, 12, 7)
        controls.setSpacing(0)
        self.slider = SeekSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setFixedHeight(18)
        controls.addWidget(self.slider)
        row = QHBoxLayout()
        row.setSpacing(6)

        def tool(name, title, callback):
            button = QToolButton()
            button.setIcon(glyph(name, "#eaf3ed"))
            button.setIconSize(QSize(18, 18))
            button.setFixedSize(30, 28)
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(callback)
            return button

        self.play_button = tool("play", "播放 / 暂停 · 空格", self.toggle)
        self.position_label = QLabel("0:00 / 0:00")
        self.mute_button = tool("volume", "静音 · M", self.toggle_mute)
        self.fullscreen = tool("expand", "全屏 · 双击画面 / F", self.toggle_fullscreen)
        self.settings_button = tool("more", "播放设置", self.show_settings)
        row.addWidget(self.play_button)
        row.addWidget(self.position_label)
        row.addStretch()
        row.addWidget(self.mute_button)
        row.addWidget(self.fullscreen)
        row.addWidget(self.settings_button)
        controls.addLayout(row)
        self.hint = QLabel(self.surface)
        self.hint.setObjectName("playerHint")
        self.hint.setWordWrap(True)
        self.hint.hide()
        self.controls.hide()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.receive_frame)
        self.player.setVideoSink(self.sink)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.slider.sliderPressed.connect(self.hide_timer_stop)
        self.slider.sliderReleased.connect(self.reveal)
        self.surface.tapped.connect(self.surface_tap)
        self.surface.toggle.connect(self.surface_double_tap)
        self.surface.seek.connect(lambda value: self.seek(int(value * max(1000, self.player.duration()))))
        self.surface.volume.connect(lambda value: self.volume_slider.setValue(self.volume_slider.value()+round(value*100)))
        self.surface.moved.connect(self.reveal)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_controls)
        self.hint_timer = QTimer(self)
        self.hint_timer.setSingleShot(True)
        self.hint_timer.timeout.connect(self.hint.hide)
        self.settings_panel = QFrame(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.settings_panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.settings_panel.setObjectName("pickerPopup")
        self.settings_panel.setStyleSheet("QFrame#pickerPopup { background: transparent; border: none; }")
        outer = QVBoxLayout(self.settings_panel)
        outer.setContentsMargins(10, 8, 10, 12)
        card = QFrame(self.settings_panel)
        card.setObjectName("playbackSettings")
        card.setStyleSheet("QFrame#playbackSettings { background: white; border: 1px solid #d4e0d6; border-radius: 12px; }")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(17, 52, 34, 35))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        settings = QVBoxLayout(card)
        settings.setContentsMargins(16, 14, 16, 14)
        settings.setSpacing(12)
        title = QLabel("播放设置")
        title.setStyleSheet("font-weight:600;color:#294e39;")
        settings.addWidget(title)
        self.rate = QComboBox()
        for rate in (.5, .75, 1., 1.25, 1.5, 2.):
            self.rate.addItem(f"{rate:g}×", rate)
        self.rate.setCurrentIndex(2)
        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("倍速"))
        rate_row.addWidget(self.rate, 1)
        settings.addLayout(rate_row)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(65)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-70, 70)
        for title, slider in (("音量", self.volume_slider), ("亮度", self.brightness_slider)):
            line = QHBoxLayout()
            line.addWidget(QLabel(title))
            line.addWidget(slider, 1)
            settings.addLayout(line)
        self.loop = QCheckBox("循环播放")
        settings.addWidget(self.loop)
        self.rotate = QPushButton("旋转画面")
        self.rotate.setIcon(glyph("rotate"))
        settings.addWidget(self.rotate)
        help_text = QLabel("空格 暂停  ·  ← → 跳转 5 秒\nF 全屏  ·  M 静音  ·  Esc 返回")
        help_text.setStyleSheet("font-size:11px;color:#7c8b80;")
        settings.addWidget(help_text)
        self.rate.currentIndexChanged.connect(lambda: self.player.setPlaybackRate(self.rate.currentData() or 1.))
        self.loop.toggled.connect(lambda checked: self.player.setLoops(QMediaPlayer.Loops.Infinite if checked else QMediaPlayer.Loops.Once))
        self.volume_slider.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        self.volume_slider.valueChanged.connect(lambda value: self.audio.setMuted(value == 0))
        self.audio.mutedChanged.connect(lambda muted: self.mute_button.setIcon(glyph("muted" if muted else "volume", "#eaf3ed")))
        self.brightness_slider.valueChanged.connect(self.change_brightness)
        self.rotate.clicked.connect(self.rotate_picture)
        self.shortcuts = []
        for key, callback in (("Space", self.toggle), ("Left", lambda: self.seek(-5000)), ("Right", lambda: self.seek(5000)),
                              ("F", self.toggle_fullscreen), ("M", self.toggle_mute), ("Escape", self.escape),
                              (Qt.Key.Key_MediaTogglePlayPause, self.toggle)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        QApplication.instance().applicationStateChanged.connect(self.app_state)

    def receive_frame(self, frame):
        self.surface.frame(frame)
        if self.surface.image.isNull() or self.loaded_frame:
            return
        self.loaded_frame = True
        self.hint.hide()
        if self.preloading:
            self.preloading = False
            self.player.pause()
            self.audio.setMuted(False)
            self.surface.paused = True
            self.surface.update()
        self.ready.emit()

    def set_source(self, url, autoplay=False, relay=None, audio=False, duration=0):
        self.clear()
        self.relay = relay
        self.has_source = True
        self.preloading = not autoplay and not audio
        self.surface.placeholder = "正在连接预览…"
        self.surface.setProperty("audio", audio)
        self.controls.show()
        self.position_label.setText("0:00 / " + time_text(duration*1000))
        self.audio.setMuted(self.preloading)
        self.player.setSource(url if isinstance(url, QUrl) else QUrl(url))
        self.player.play()
        if not autoplay and audio:
            self.player.pause()

    def set_poster(self, image):
        if not self.loaded_frame and not image.isNull():
            self.surface.image = image
            self.surface.paused = True
            self.surface.update()

    def clear(self):
        self.hide_timer.stop()
        self.has_source = False
        self.preloading = False
        self.loaded_frame = False
        self.resume_when_active = False
        self.player.stop()
        self.player.setSource(QUrl())
        self.audio.setMuted(False)
        self.surface.image = QImage()
        self.surface.rotation = 0
        self.surface.paused = True
        self.surface.placeholder = "粘贴分享链接，画面会出现在这里"
        self.surface.update()
        self.slider.setRange(0, 0)
        self.position_label.setText("0:00 / 0:00")
        self.settings_panel.hide()
        self.controls.hide()
        self.hint.hide()
        if self.relay:
            self.relay.close()
            self.relay = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(240, self.surface.width()-24)
        self.controls.setGeometry(12, self.surface.height()-83, width, 71)
        self.hint.setGeometry(20, 18, max(200, self.surface.width()-40), 44)

    def position_changed(self, value):
        if not self.slider.isSliderDown():
            self.slider.setValue(value)
        self.position_label.setText(time_text(value) + " / " + time_text(self.player.duration()))

    def duration_changed(self, value):
        self.slider.setRange(0, value)
        self.position_changed(self.player.position())

    def toggle(self):
        if not self.has_source:
            return
        was_preloading = self.preloading
        self.preloading = False
        if was_preloading:
            self.audio.setMuted(False)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()
        self.reveal()

    def surface_tap(self):
        self._tap_state = self.player.playbackState()
        self._tap_time = time.monotonic()
        self.toggle()

    def surface_double_tap(self):
        # The first click responds immediately. A double click restores the
        # previous playback state and changes only the viewing mode.
        if time.monotonic()-getattr(self, "_tap_time", 0) < QApplication.doubleClickInterval()/1000:
            if self._tap_state == QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()
            else:
                self.player.pause()
        self.toggle_fullscreen()

    def state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState and not self.preloading
        self.play_button.setIcon(glyph("pause" if playing else "play", "#eaf3ed"))
        self.surface.paused = not playing
        self.surface.update()
        if self.has_source:
            self.reveal()

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.StalledMedia:
            self.show_hint("正在缓冲…")
        elif status in (QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.EndOfMedia):
            self.hint.hide()

    def media_error(self, error, message):
        if self.has_source and error != QMediaPlayer.Error.NoError:
            self.preloading = False
            self.show_hint("预览暂不可用，可重试或直接保存", 0)
            self.failed.emit("预览暂不可用，可重试或直接保存。")

    def show_hint(self, text, timeout=1800):
        self.hint.setText(text)
        self.hint.show()
        self.hint.raise_()
        if timeout:
            self.hint_timer.start(timeout)

    def seek(self, delta):
        self.player.setPosition(max(0, min(self.player.duration(), self.player.position()+delta)))
        self.reveal()

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())

    def rotate_picture(self):
        self.surface.rotation = (self.surface.rotation + 90) % 360
        self.surface.update()

    def change_brightness(self, value):
        self.surface.brightness = value / 100
        self.surface.update()

    def show_settings(self):
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            return
        self.hide_timer.stop()
        self.settings_panel.adjustSize()
        self.settings_panel.setFixedWidth(280)
        point = self.settings_button.mapToGlobal(QPoint(self.settings_button.width(), 0))
        screen = self.screen().availableGeometry()
        self.settings_panel.move(max(screen.left()+8, min(point.x()-280, screen.right()-288)),
                                 max(screen.top()+8, point.y()-self.settings_panel.height()-10))
        self.settings_panel.show()

    def is_fullscreen(self):
        return bool(self.fullscreen_window or (self.fullscreen_owner and self.fullscreen_owner.isFullScreen()))

    def toggle_fullscreen(self):
        if not self.has_source:
            return
        self.settings_panel.hide()
        if self.is_fullscreen():
            self.exit_fullscreen()
            return
        if self.fullscreen_owner:
            self.fullscreen_owner.showFullScreen()
        else:
            self._dock_parent = self.parentWidget()
            self._dock_index = self._dock_parent.layout().indexOf(self)
            host = FullscreenWindow(self.window())
            host.setWindowTitle("拾影 · 全屏预览")
            host.media = self
            box = QVBoxLayout(host)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(self)
            self.fullscreen_window = host
            host.showFullScreen()
            self.show()
        self.fullscreen.setIcon(glyph("collapse", "#eaf3ed"))
        self.setFocus()
        self.hide_controls()

    def exit_fullscreen(self):
        if self.fullscreen_owner:
            self.fullscreen_owner.showNormal()
        elif self.fullscreen_window:
            host = self.fullscreen_window
            self.fullscreen_window = None
            self.setParent(self._dock_parent)
            self._dock_parent.layout().insertWidget(self._dock_index, self)
            if hasattr(self._dock_parent, "setCurrentWidget"):
                self._dock_parent.setCurrentWidget(self)
            self.show()
            host.hide()
            host.deleteLater()
        self.fullscreen.setIcon(glyph("expand", "#eaf3ed"))
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.reveal()

    def hide_timer_stop(self):
        self.hide_timer.stop()

    def reveal(self):
        if not self.has_source:
            return
        self.controls.show()
        self.controls.raise_()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and not self.preloading:
            self.hide_timer.start(2400)

    def hide_controls(self):
        if not self.settings_panel.isVisible() and not self.slider.isSliderDown():
            if self.controls.underMouse():
                self.hide_timer.start(800)
                return
            if self.is_fullscreen() or self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.controls.hide()

    def escape(self):
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
        elif self.is_fullscreen():
            self.exit_fullscreen()
        elif self.fullscreen_owner:
            self.fullscreen_owner.close()

    def app_state(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.resume_when_active = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and not self.preloading
            self.player.pause()
        elif self.resume_when_active:
            self.resume_when_active = False
            self.player.play()
        elif self.preloading and self.has_source:
            self.player.play()

    def dispose(self):
        if self.fullscreen_window:
            self.exit_fullscreen()
        self.clear()
        self.hint_timer.stop()
        try:
            QApplication.instance().applicationStateChanged.disconnect(self.app_state)
        except RuntimeError:
            pass
        self.player.setVideoSink(None)


class PlayerDialog(QDialog):
    def __init__(self, result, title, parent=None):
        super().__init__(parent)
        self.result = result
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title + " · 拾影播放器")
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.media = PlayerWidget(self, fullscreen_owner=self)
        layout.addWidget(self.media)
        for name in ("player", "audio", "surface", "controls", "rate", "brightness_slider", "loop", "slider", "rotate", "play_button"):
            setattr(self, name, getattr(self.media, name))
        self.media.set_source(QUrl.fromLocalFile(str(Path(result.path).resolve())), autoplay=True, audio=result.kind == "audio")

    def seek(self, delta):
        self.media.seek(delta)

    def rotate_picture(self):
        self.media.rotate_picture()

    def toggle_fullscreen(self):
        self.media.toggle_fullscreen()

    def escape(self):
        self.media.escape()

    def reject(self):
        self.close()

    def closeEvent(self, event):
        self.media.dispose()
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
