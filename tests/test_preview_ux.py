import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
import requests
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QToolButton

from clipharbor.douyin import video_from_payload
from clipharbor.engine import Engine
from clipharbor.gui import Window, STYLE
from clipharbor.media import run_ffmpeg
from clipharbor.models import AppError, ImageAsset, VideoFormat, VideoInfo
from clipharbor.platforms import douyin_album, image_asset
from clipharbor.player import PlayerWidget
from clipharbor.preview import PreviewRelay
from clipharbor.store import Store
from clipharbor.watermark import marked_url
from clipharbor.widgets import ShareInput


def test_android_browser_readers_are_ported_without_behavior_drift():
    root = Path(__file__).resolve().parent.parent
    for name in ("browser_capture.js", "browser_read.js"):
        assert (root/"clipharbor"/name).read_text(encoding="utf-8") == (root/"android/app/src/main/assets"/name).read_text(encoding="utf-8")


def test_no_watermarked_douyin_download_or_backup_fallback():
    node = {"aweme_id": "123", "video": {
        "download_addr": {"url_list": ["https://cdn.example/download.mp4"]},
        "play_addr": {"url_list": ["https://aweme.example/playwm/?video_id=123"]}}}
    assert video_from_payload(node, "123", "", "") is None
    node["video"]["play_addr_h264"] = {"url_list": ["https://cdn.example/clean.mp4", "https://cdn.example/v.mp4?watermark=1"]}
    info = video_from_payload(node, "123", "", "")
    assert len(info.formats) == 1 and info.formats[0].url.endswith("clean.mp4")
    assert not info.formats[0].alternatives


def test_album_uses_original_and_refuses_owner_watermark():
    marked = {"url_list": ["https://cdn.example/owner-watermark.jpg"]}
    clean = {"url_list": ["https://cdn.example/original.jpg"]}
    node = {"images": [{"owner_watermark_image": marked, "origin_image": clean}]}
    info = douyin_album(node, "123", "", "")
    assert info.images[0].url.endswith("original.jpg")
    assert douyin_album({"images": [{"owner_watermark_image": marked}]}, "123", "", "") is None
    assert image_asset({"urlDefault": "https://cdn.example/a.jpg?x-oss-process=image%2Fwatermark,text_x", "infoList": [{"url": "https://cdn.example/original.jpg"}] }).url.endswith("original.jpg")
    assert not marked_url("https://cdn.example/a.mp4?watermark=0")


def test_watermark_guard_runs_before_any_network_or_file_write(tmp_path):
    fmt = VideoFormat("0", "video", "https://cdn.example/playwm/?id=123")
    with pytest.raises(AppError, match="水印"):
        Engine(tmp_path).download(VideoInfo("", "", "123", "test"), fmt, tmp_path/"saved")
    assert not (tmp_path/"saved").exists()


def test_preview_relay_forwards_ranges_headers_and_never_accepts_arbitrary_urls(tmp_path):
    received = []
    payload = bytes(range(256))*100

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            received.append((self.path, self.headers.get("Range"), self.headers.get("Referer")))
            data = payload[128:256]
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Range", f"bytes 128-255/{len(payload)}")
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    relay = PreviewRelay(tmp_path, VideoFormat("0", "video", f"http://127.0.0.1:{server.server_port}/only.mp4", headers={"Referer": "https://example.org/post/123"}))
    try:
        response = requests.get(relay.url, headers={"Range": "bytes=128-255"}, timeout=3)
        assert response.status_code == 206 and response.content == payload[128:256]
        assert response.headers["Content-Range"] == f"bytes 128-255/{len(payload)}"
        assert received == [("/only.mp4", "bytes=128-255", "https://example.org/post/123")]
        assert requests.get(relay.url+"?url=https://example.org/other", timeout=3).status_code == 404
        assert not list(tmp_path.iterdir())  # Relay never creates a full-file cache.
    finally:
        relay.close()
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def qt():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def spin(app, predicate, timeout=6):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    assert predicate()


def test_inline_preview_first_frame_pause_immediate_tap_fullscreen_and_clear(qt, tmp_path):
    path = tmp_path/"video.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=160x90:r=15", "-t", "3", "-an", "-c:v", "libx264", "-movflags", "+faststart", path], Event())
    store = Store(tmp_path/"data")
    window = Window(store)
    window.show()
    # Test the real local-media path while avoiding any external network.
    from PySide6.QtCore import QUrl
    media = window.inline_preview.media
    media.set_source(QUrl.fromLocalFile(str(path)))
    spin(qt, lambda: media.loaded_frame)
    assert media.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert not window.viewers and not store.records()
    assert len(media.controls.findChildren(QToolButton)) == 4
    QTest.mouseClick(media.surface, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
    assert qt.focusWidget() is media.surface
    assert media.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    media.player.pause()
    QTest.keyClick(media.surface, Qt.Key.Key_F)
    qt.processEvents()
    assert media.fullscreen_window and media.is_fullscreen()
    assert media.isVisible() and media.surface.isVisible()
    QTest.keyClick(media, Qt.Key.Key_Escape)
    qt.processEvents()
    assert not media.is_fullscreen() and window.inline_preview.layout().indexOf(window.inline_preview.stack) >= 0
    window.clear_input()
    assert not media.has_source and media.surface.image.isNull()
    assert not store.records()
    window.close()


def test_ctrl_enter_does_not_submit_during_chinese_composition(qt):
    entry = ShareInput()
    calls = []
    entry.submitted.connect(lambda: calls.append(True))
    entry.setPlainText("分享链接")
    entry.inputMethodEvent(QInputMethodEvent("拼音", []))
    QTest.keyClick(entry, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert calls == []
    entry.inputMethodEvent(QInputMethodEvent("", []))
    QTest.keyClick(entry, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert calls == [True]
    entry.close()
