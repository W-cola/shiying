import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event

import pytest

from clipharbor.engine import Engine
from clipharbor.links import safe_filename, stable_id
from clipharbor.models import AppError, Cancelled, VideoFormat, VideoInfo

PAYLOAD = b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 4096


@pytest.fixture
def server():
    observations = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            observations.append(dict(self.headers))
            if self.path == "/error":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>Please log in</html>")
                return
            offset = 0
            use_range = self.headers.get("Range") and self.path != "/ignore-range"
            if use_range:
                offset = int(self.headers["Range"].split("=")[1].rstrip("-"))
            self.send_response(206 if use_range else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(PAYLOAD) - offset))
            self.send_header("ETag", '"test-video"')
            if use_range:
                self.send_header("Content-Range", f"bytes {0 if self.path == '/bad-range' else offset}-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
            self.end_headers()
            try:
                self.wfile.write(PAYLOAD[offset:])
            except (BrokenPipeError, ConnectionResetError):
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", observations
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def prepare(tmp_path, url):
    data = tmp_path / "data"
    data.mkdir()
    folder = tmp_path / "videos"
    folder.mkdir()
    fmt = VideoFormat("test", "测试画质", url)
    info = VideoInfo(url, url, "123", "测试视频", formats=[fmt])
    return Engine(data), info, fmt, folder


def seed_partial(folder, info, fmt):
    stem = safe_filename(info.title, info.video_id)
    path = folder / f"{stem}.{stable_id(fmt.key + ':' + fmt.url)}.part"
    path.write_bytes(PAYLOAD[:170000])
    path.with_suffix(".part.json").write_text(json.dumps({"url": fmt.url, "validator": '"test-video"'}))
    return path


def test_real_stream_download_and_no_overwrite(server, tmp_path):
    base, _ = server
    engine, info, fmt, folder = prepare(tmp_path, base + "/video")
    first = engine.download(info, fmt, folder)
    second = engine.download(info, fmt, folder)
    assert first != second
    assert first.read_bytes() == second.read_bytes() == PAYLOAD
    assert not list(folder.glob("*.part*"))


@pytest.mark.parametrize("route", ["/video", "/ignore-range"])
def test_resume_or_clean_restart_when_range_ignored(server, tmp_path, route):
    base, requests_seen = server
    engine, info, fmt, folder = prepare(tmp_path, base + route)
    seed_partial(folder, info, fmt)
    path = engine.download(info, fmt, folder)
    assert path.read_bytes() == PAYLOAD
    assert requests_seen[0]["Range"] == "bytes=170000-"
    assert requests_seen[0]["If-Range"] == '"test-video"'


def test_error_page_is_never_saved_as_video(server, tmp_path):
    base, _ = server
    engine, info, fmt, folder = prepare(tmp_path, base + "/error")
    with pytest.raises(AppError, match="服务器返回"):
        engine.download(info, fmt, folder)
    assert not list(folder.glob("*.mp4"))


def test_cancellation_preserves_partial_and_can_resume(server, tmp_path):
    base, _ = server
    engine, info, fmt, folder = prepare(tmp_path, base + "/video")
    engine.progress = lambda p: engine.cancel.set()
    with pytest.raises(Cancelled):
        engine.download(info, fmt, folder)
    assert list(folder.glob("*.part"))
    assert not list(folder.glob("*.mp4"))
    engine.cancel.clear()
    engine.progress = lambda p: None
    assert engine.download(info, fmt, folder).read_bytes() == PAYLOAD


def test_cookie_scope_is_preserved(tmp_path):
    from clipharbor.douyin import make_session
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"cookies": [{"name": "sessionid", "value": "private-test",
        "domain": ".douyin.com", "path": "/", "secure": True, "expires": -1}]}))
    import requests
    with make_session(state) as session:
        request = session.prepare_request(requests.Request("GET", "https://cdn.example.org/video.mp4"))
        assert "Cookie" not in request.headers
        request = session.prepare_request(requests.Request("GET", "https://www.douyin.com/video/123"))
        assert request.headers["Cookie"] == "sessionid=private-test"


def test_bad_content_range_does_not_produce_corrupt_video(server, tmp_path):
    base, _ = server
    engine, info, fmt, folder = prepare(tmp_path, base + "/bad-range")
    partial = seed_partial(folder, info, fmt)
    with pytest.raises(AppError, match="续传响应不一致"):
        engine.download(info, fmt, folder)
    assert partial.read_bytes() == PAYLOAD[:170000]
    assert not list(folder.glob("*.mp4"))


def test_generic_ytdlp_resolution_and_download(server, tmp_path, monkeypatch):
    base, _ = server
    engine, _, _, folder = prepare(tmp_path, base + "/video.mp4")
    monkeypatch.setattr("clipharbor.engine.shutil.which", lambda name: None)
    info = engine.resolve(base + "/video.mp4")
    assert info.engine == "yt-dlp"
    assert info.formats
    result = engine.download(info, info.formats[0], folder)
    assert result.read_bytes() == PAYLOAD
