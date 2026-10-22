"""Local range relay for instant preview with the source's normal HTTP headers.

Qt's media backend takes a URL, not per-source cookies/Referer. This relay serves
one opaque local URL and forwards only that selected source. No complete media
download, user history entry, or remote parsing service is involved.
"""
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import urlsplit

import requests

from .douyin import make_session, DESKTOP_UA
from .watermark import marked_url


def can_stream(info, fmt):
    return (info.kind != "images" and fmt.mode == "direct" and not fmt.decode_key
            and bool(fmt.url) and ".m3u8" not in urlsplit(fmt.url).path.lower())


class PreviewRelay:
    def __init__(self, data_dir, fmt):
        self.stopped = Event()
        self.path = "/" + secrets.token_urlsafe(24) + "/preview." + ("webm" if fmt.ext == "webm" else "mp4")
        relay = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def serve(self, body):
                if self.path != relay.path or relay.stopped.is_set():
                    self.send_error(404)
                    return
                byte_range = self.headers.get("Range", "")
                if byte_range and not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range):
                    self.send_error(416)
                    return
                headers = {"User-Agent": DESKTOP_UA, **fmt.headers, "Accept-Encoding": "identity"}
                if byte_range:
                    headers["Range"] = byte_range
                response = None
                with make_session(data_dir / "browser-state.json") as session:
                    for url in [fmt.url, *fmt.alternatives]:
                        try:
                            response = session.get(url, headers=headers, stream=True, timeout=(6, 8))
                            if response.status_code in (200, 206, 416) and not marked_url(response.url):
                                break
                            response.close()
                            response = None
                        except requests.RequestException:
                            response = None
                    if response is None:
                        self.send_error(502, "Preview source unavailable")
                        return
                    with response:
                        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                            self.send_error(502, "Unexpected media encoding")
                            return
                        mime = response.headers.get("Content-Type", "").lower()
                        if response.status_code != 416 and any(t in mime for t in ("text/", "json")):
                            self.send_error(502, "Source did not return media")
                            return
                        self.send_response(response.status_code)
                        for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
                            if name in response.headers:
                                self.send_header(name, response.headers[name])
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.close_connection = True
                        if body:
                            try:
                                for chunk in response.iter_content(16 * 1024):
                                    if relay.stopped.is_set():
                                        break
                                    if chunk:
                                        self.wfile.write(chunk)
                                        self.wfile.flush()
                            except (OSError, requests.RequestException):
                                pass  # Normal when the player seeks or changes source.

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}{self.path}"

    def close(self):
        if self.stopped.is_set():
            return
        self.stopped.set()

        def shutdown():
            self.server.shutdown()
            self.server.server_close()

        Thread(target=shutdown, daemon=True).start()
