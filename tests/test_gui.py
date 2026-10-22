import os
import time
from pathlib import Path
from threading import Event

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QMessageBox

from clipharbor.gui import Window, STYLE
from clipharbor.media import run_ffmpeg
from clipharbor.models import SavedMedia, VideoFormat, VideoInfo
from clipharbor.player import GalleryDialog, PlayerDialog
from clipharbor.store import Store


@pytest.fixture(scope='module')
def qt():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    yield app


def spin(app, predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.025)
    assert predicate()


def test_real_player_decode_pause_rate_seek_fullscreen_and_cleanup(qt, tmp_path):
    cache = tmp_path/'preview-cache'
    cache.mkdir()
    path = cache/'video.mp4'
    run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=15', '-f', 'lavfi', '-i', 'sine=frequency=440',
                '-t', '4', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', path], Event())
    dialog = PlayerDialog(SavedMedia(path, [path], 'video', True, cache), '播放器验证')
    dialog.show()
    spin(qt, lambda: dialog.player.duration() > 3000 and not dialog.surface.image.isNull())
    assert dialog.player.error() == QMediaPlayer.Error.NoError
    spin(qt, lambda: dialog.player.position() > 150)
    dialog.player.pause()
    dialog.rate.setCurrentIndex(4)
    qt.processEvents()
    assert dialog.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert dialog.player.playbackRate() == 1.5
    dialog.seek(1000)
    assert dialog.player.position() >= 1000
    dialog.rotate_picture()
    assert dialog.surface.rotation == 90
    dialog.brightness_slider.setValue(20)
    assert dialog.surface.brightness == .2
    dialog.loop.setChecked(True)
    assert dialog.player.loops() == QMediaPlayer.Loops.Infinite
    dialog.toggle_fullscreen()
    qt.processEvents()
    assert dialog.isFullScreen() and not dialog.controls.isVisible()
    dialog.escape()
    assert not dialog.isFullScreen()
    dialog.close()
    qt.processEvents()
    assert not cache.exists()


def test_gallery_navigation_and_close_keeps_saved_files(qt, tmp_path):
    files = []
    for i, color in enumerate(('red', 'blue')):
        path = tmp_path/f'{i}.png'
        image = QImage(64, 96, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        image.save(str(path))
        files.append(path)
    gallery = GalleryDialog(SavedMedia(tmp_path, files, 'images'), '图文', '正文')
    gallery.show()
    qt.processEvents()
    assert not gallery.pixmap.isNull() and gallery.count.text() == '1 / 2'
    gallery.move(1)
    assert gallery.count.text() == '2 / 2' and not gallery.next.isEnabled()
    gallery.move(1)
    assert gallery.index == 1
    gallery.move(-1)
    assert gallery.index == 0 and not gallery.previous.isEnabled()
    gallery.close()
    assert all(p.exists() for p in files)


def test_library_search_filter_clear_and_confirmed_delete(qt, tmp_path, monkeypatch):
    store = Store(tmp_path/'data')
    video = tmp_path/'old.mp4'
    video.write_bytes(b'existing')
    info = VideoInfo('https://example.org/v', 'https://example.org/v', '123', '收藏标题', '作者', platform='抖音')
    store.add_history(info, video)
    window = Window(store)
    window.show()
    qt.processEvents()
    assert window.history.rowCount() == 1
    window.history_search.setText('没有匹配')
    assert window.history.rowCount() == 0
    window.history_search.setText('作者')
    assert window.history.rowCount() == 1
    window.history_kind.setCurrentIndex(3)
    assert window.history.rowCount() == 0
    window.history_kind.setCurrentIndex(0)
    window.operation = 'resolve'
    info.formats = [VideoFormat('0', '原始', 'https://example.org/v.mp4')]
    window.completed(info)
    window.clear_input()
    assert window.info is None and not window.preview_button.isEnabled()
    window.history.selectRow(0)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **kw: QMessageBox.StandardButton.Cancel)
    window.delete_record()
    assert video.exists() and window.history.rowCount() == 1
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **kw: QMessageBox.StandardButton.Yes)
    window.delete_record()
    assert not video.exists() and window.history.rowCount() == 0
    window.close()
