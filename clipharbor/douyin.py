"""Read normal share pages and the media exposed by their own player.

No private signing API, external parsing service, or CAPTCHA solver is used.
"""
import html
import json
import re
import time
from pathlib import Path
from threading import Event
from urllib.parse import unquote, urlsplit

import requests

from .links import douyin_id, is_douyin, stable_id
from .models import AppError, Cancelled, VideoFormat, VideoInfo

DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"


def make_session(state_path: Path | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": DESKTOP_UA})
    if state_path and state_path.exists():
        try:
            for cookie in json.loads(state_path.read_text(encoding="utf-8")).get("cookies", []):
                expires = cookie.get("expires", -1)
                if expires > 0 and expires < time.time():
                    continue
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"],
                                    path=cookie.get("path", "/"), secure=cookie.get("secure", False))
        except (ValueError, OSError, KeyError):
            pass
    return session


def walk(value):
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))


def script_payloads(page_html: str) -> list:
    payloads = []
    for attrs, content in re.findall(r"<script\b([^>]*)>(.*?)</script>", page_html, re.S | re.I):
        if re.search(r"(?:RENDER_DATA|__NEXT_DATA__|SIGI_STATE|application/json)", attrs, re.I):
            for candidate in (content, unquote(content), html.unescape(content)):
                try:
                    payloads.append(json.loads(candidate.strip()))
                    break
                except ValueError:
                    continue
        for match in re.finditer(r"(?:window\.)?(?:_ROUTER_DATA|_SSR_DATA|__INITIAL_STATE__|__INITIAL_SSR_STATE__|__APOLLO_STATE__|INIT_STATE|__INITIAL_DATA__|__NEXT_DATA__|__playinfo__)\s*=\s*", content):
            try:
                # Replace JavaScript's undefined only outside quoted strings.
                state = re.sub(r'"(?:\\.|[^"\\])*"|\bundefined\b', lambda m: "null" if m[0] == "undefined" else m[0], content[match.end():].lstrip())
                if state.startswith("JSON.parse("):
                    encoded = json.JSONDecoder().raw_decode(state[len("JSON.parse("):])[0]
                    payloads.append(json.loads(encoded))
                else:
                    payloads.append(json.JSONDecoder().raw_decode(state)[0])
            except ValueError:
                continue
    return payloads


def _number(value) -> int:
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def _urls(addr) -> list[str]:
    if not isinstance(addr, dict):
        return []
    return list(dict.fromkeys(u for u in (addr.get("url_list") or addr.get("urlList") or addr.get("UrlList") or [])
                             if isinstance(u, str) and u.startswith(("https://", "http://"))))


def video_from_payload(payload, target_id: str, source_url: str, page_url: str) -> VideoInfo | None:
    for node in walk(payload):
        node_id = str(node.get("aweme_id") or node.get("awemeId") or node.get("id") or "")
        if target_id and node_id != target_id:
            continue
        if node.get("has_drm") or node.get("drm") or node.get("is_live"):
            continue
        if node.get("images") or node.get("image_post_info"):
            from .platforms import douyin_album
            info = douyin_album(node, node_id, source_url, page_url)
            if info:
                return info
        video = node.get("video")
        if not isinstance(video, dict) or not node_id:
            continue
        formats = []
        seen = set()

        def add(addr, label, owner=None):
            urls = _urls(addr)
            if not urls or urls[0] in seen:
                return
            owner = owner or video
            seen.update(urls)
            width = _number(addr.get("width") or owner.get("width") or video.get("width"))
            height = _number(addr.get("height") or owner.get("height") or video.get("height"))
            size = _number(addr.get("data_size") or addr.get("dataSize") or addr.get("DataSize"))
            # VVC/bytevc2 is not widely playable. Prefer AVC and HEVC sources.
            if "bytevc2" in str(addr.get("url_key") or addr.get("UrlKey") or ""):
                return
            dimensions = f" · {width}×{height}" if width and height else ""
            formats.append(VideoFormat(str(len(formats)), label + dimensions, urls[0],
                                       height=height, width=width, size=size,
                                       headers={"User-Agent": DESKTOP_UA, "Referer": page_url}, alternatives=urls[1:]))

        for entry in video.get("bit_rate") or video.get("bitRate") or video.get("bitrateInfo") or []:
            add(entry.get("play_addr") or entry.get("playAddr") or entry.get("PlayAddr") or {},
                entry.get("gear_name") or entry.get("gearName") or "播放画质", entry)
        for key, label in (("play_addr_h264", "兼容画质"), ("play_addr", "播放画质"),
                           ("playAddr", "播放画质"), ("play_addr_bytevc1", "HEVC 画质"),
                           ("download_addr", "分享页下载画质")):
            add(video.get(key) or {}, label)
        if not formats:
            continue
        formats.sort(key=lambda f: (f.height, f.size), reverse=True)
        cover = video.get("origin_cover") or video.get("cover") or {}
        covers = _urls(cover)
        author = node.get("author") or {}
        return VideoInfo(source_url, page_url, node_id, node.get("desc") or node.get("description") or f"抖音视频 {node_id}",
                         author.get("nickname", ""), _number(video.get("duration")) / 1000,
                         covers[0] if covers else "", "抖音", "direct", formats)
    return None


def check_cancel(cancel: Event):
    if cancel.is_set():
        raise Cancelled("任务已取消。")


class DouyinResolver:
    def __init__(self, data_dir: Path, log, cancel: Event):
        self.data_dir, self.log, self.cancel = data_dir, log, cancel
        self.state = data_dir / "browser-state.json"

    def resolve_share(self, source: str) -> tuple[str, str, VideoInfo | None]:
        self.log("正在展开分享链接…")
        with make_session(self.state) as session:
            response = session.get(source, timeout=(12, 18), headers={"User-Agent": MOBILE_UA})
            response.raise_for_status()
            check_cancel(self.cancel)
            if not is_douyin(response.url):
                raise AppError("分享链接没有跳转到抖音视频页面，请检查链接。")
            target = douyin_id(response.url) or douyin_id(source)
            if not target:
                raise AppError("未找到内容编号。请打开分享链接，复制单条视频或图文的网页地址。")
            canonical = f"https://www.douyin.com/video/{target}"
            for payload in script_payloads(response.text):
                info = video_from_payload(payload, target, source, canonical)
                if info:
                    return canonical, target, info
            # Read the ordinary mobile share page, which may expose server-rendered metadata.
            try:
                mobile = session.get(f"https://www.iesdouyin.com/share/video/{target}/", timeout=(10, 15),
                                     headers={"User-Agent": MOBILE_UA})
                if mobile.ok:
                    for payload in script_payloads(mobile.text):
                        info = video_from_payload(payload, target, source, canonical)
                        if info:
                            return canonical, target, info
            except requests.RequestException:
                pass
            return canonical, target, None

    def browser(self, source: str, canonical: str = "", target: str = "", interactive=False) -> VideoInfo:
        from playwright.sync_api import sync_playwright, Error as BrowserError

        self.log("打开独立浏览器，请在页面中播放目标视频；如需验证或登录，请手动完成。" if interactive else "分享页没有直接提供视频，正在用浏览器读取播放器…")
        with sync_playwright() as p:
            context = None
            failures = []
            for channel in ("msedge", "chrome", None):
                try:
                    context = p.chromium.launch_persistent_context(
                        str(self.data_dir / "browser-profile"), channel=channel,
                        headless=not interactive, viewport={"width": 1280, "height": 840},
                        locale="zh-CN", accept_downloads=False)
                    break
                except BrowserError as error:
                    failures.append(str(error))
            if not context:
                raise AppError("无法启动浏览器。请安装 Microsoft Edge 或 Chrome；开发者也可以运行 playwright install chromium。")
            candidate = [None]
            page = context.pages[0] if context.pages else context.new_page()
            observed_id = [target or douyin_id(canonical) or douyin_id(source)]

            def on_response(response):
                if candidate[0] or not observed_id[0]:
                    return
                if not any(part in response.url for part in ("aweme/", "/detail", "video")):
                    return
                try:
                    if "json" in response.headers.get("content-type", "") and _number(response.headers.get("content-length")) < 5_000_000:
                        info = video_from_payload(response.json(), observed_id[0], source, page.url)
                        if info:
                            candidate[0] = info
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                try:
                    page.goto(canonical or source, wait_until="domcontentloaded", timeout=30000)
                except BrowserError:
                    if page.is_closed():
                        raise AppError("浏览器已关闭，未完成解析。")
                deadline = time.monotonic() + (180 if interactive else 24)
                while time.monotonic() < deadline:
                    check_cancel(self.cancel)
                    if page.is_closed():
                        raise AppError("浏览器已关闭，未完成解析。")
                    current_id = douyin_id(page.url)
                    if not observed_id[0] and current_id:
                        observed_id[0] = current_id
                    if candidate[0]:
                        self._save_state(context)
                        return candidate[0]
                    # Only use the player on the requested video's own page.
                    if current_id and current_id == observed_id[0]:
                        try:
                            payloads = page.evaluate("() => [window._ROUTER_DATA, window.__INITIAL_STATE__].filter(Boolean)")
                            payloads.extend(script_payloads(page.content()))
                            for payload in payloads:
                                info = video_from_payload(payload, observed_id[0], source, page.url)
                                if info:
                                    self._save_state(context)
                                    return info
                            page.evaluate("""() => {
                                const vs = [...document.querySelectorAll('video')].filter(v => v.getBoundingClientRect().width > 0);
                                vs.sort((a,b) => b.getBoundingClientRect().width*b.getBoundingClientRect().height-a.getBoundingClientRect().width*a.getBoundingClientRect().height);
                                const v = vs[0]; if (!v) return null;
                                v.muted = true; v.play().catch(()=>{});
                                return null;
                            }""")
                            # Playing can trigger target-bound JSON, but currentSrc alone
                            # can be a loading animation or recommendation. Never return it.
                        except BrowserError:
                            pass
                    page.wait_for_timeout(600)
                self._save_state(context)
                raise AppError("没有读到目标内容的完整媒体。请点击「浏览器辅助解析」，完成登录或验证后再读取。直播和受保护内容不支持保存。")
            finally:
                context.close()

    def _save_state(self, context):
        temp = self.state.with_suffix(".tmp")
        context.storage_state(path=str(temp))
        temp.replace(self.state)
