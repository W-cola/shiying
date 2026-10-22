"""Target-bound share-page parsing shared by desktop download and preview.

The formats below follow the Android core. Only URLs actually exposed by the
target post are used; recommendations, covers and protected previews are not media.
"""
import html
import json
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from .douyin import DESKTOP_UA, MOBILE_UA, check_cancel, make_session, script_payloads, video_from_payload, walk
from .links import douyin_id, is_douyin, stable_id
from .models import AppError, ImageAsset, VideoFormat, VideoInfo
from .watermark import marked_metadata, marked_url


def host(url, domain):
    value = (urlsplit(url).hostname or "").lower()
    return value == domain or value.endswith("." + domain)


def platform(url):
    for name, domains in (("抖音", ("douyin.com", "iesdouyin.com")),
                          ("小红书", ("xiaohongshu.com", "xhslink.com")),
                          ("B站", ("bilibili.com", "b23.tv")),
                          ("快手", ("kuaishou.com", "gifshow.com", "kwai.com", "chenzhongtech.com")),
                          ("视频号", ("channels.weixin.qq.com", "finder.video.qq.com"))):
        if any(host(url, d) for d in domains):
            return name
    return "视频号" if host(url, "weixin.qq.com") and urlsplit(url).path.startswith("/sph/") else ""


def content_id(url):
    if is_douyin(url):
        return douyin_id(url)
    path, query = urlsplit(url).path, parse_qs(urlsplit(url).query)
    name = platform(url)
    pattern = {"小红书": r"/(?:explore|discovery/item)/([a-fA-F0-9]{24})(?:/|$)",
               "快手": r"/(?:short-video|fw/photo|photo)/([A-Za-z0-9_-]+)",
               "B站": r"/(?:video/)?(BV[0-9A-Za-z]{10}|av[0-9]+)(?:/|$)",
               "视频号": r"/(?:sph|feed|video)/([A-Za-z0-9_-]+)"}.get(name)
    match = re.search(pattern, path) if pattern else None
    if match:
        return match[1]
    if name == "B站":
        match = re.search(r"/(?:opus/|read/cv)(\d+)", path)
        if match:
            return ("cv" if "/read/cv" in path else "opus") + match[1]
        if host(url, "t.bilibili.com") and path.strip("/").isdigit():
            return "opus" + path.strip("/")
    for key in (("photoId", "photo_id") if name == "快手" else ("bvid", "objectId", "object_id", "feedId", "eid", "id")):
        if query.get(key):
            return query[key][0]
    return ""


def media_url(raw):
    if not isinstance(raw, str):
        return ""
    raw = html.unescape(raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        return ""
    # Upgrade only known media CDNs, preserving arbitrary direct HTTP links.
    if parts.scheme == "http" and any(host(raw, d) for d in ("xhscdn.com", "xhscdn.net", "kwimgs.com", "yximgs.com", "bilivideo.com", "hdslb.com", "qpic.cn")):
        raw = "https:" + raw[5:]
    return raw


def first(node, *keys):
    return next((node[k] for k in keys if isinstance(node.get(k), str) and node[k]), "")


def number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def image_asset(item):
    if isinstance(item, str):
        return ImageAsset(media_url(item)) if media_url(item) and not marked_url(item) else None
    if not isinstance(item, dict) or marked_metadata(item):
        return None
    variants = item.get("infoList") or []
    preferred = next((x.get("url") for x in variants if x.get("imageScene") == "WB_DFT" and x.get("url")), "")
    urls = item.get("url_list") or item.get("urlList") or []
    cdns = item.get("cdnUrls") or []
    candidates = [preferred, first(item, "originalUrl", "originUrl"), first(item, "urlDefault", "url", "urlPre", "src", "imageUrl", "picUrl"),
                  *urls, *(x.get("url", "") for x in cdns if isinstance(x, dict)),
                  *(x.get("url", "") for x in variants if isinstance(x, dict)), *(item.get("alternatives") or [])]
    candidates = list(dict.fromkeys(u for x in candidates if (u := media_url(x)) and not marked_url(u)))
    if not candidates:
        return None
    return ImageAsset(candidates[0], number(item.get("width") or item.get("w")), number(item.get("height") or item.get("h")), candidates[1:])


def album(info, items):
    if not items or not isinstance(items, list):
        return None
    images = [image_asset(item) for item in items]
    if any(x is None for x in images):
        return None  # Never silently save an incomplete album.
    info.kind, info.images = "images", images
    info.thumbnail = info.thumbnail or images[0].url
    headers = {"User-Agent": DESKTOP_UA, "Referer": info.page_url}
    info.formats = [VideoFormat("images", f"全部图片 · {len(images)} 张", images[0].url, headers=headers,
                                image_indices=list(range(len(images))))]
    info.formats.extend(VideoFormat(f"image-{i}", f"第 {i+1} 张", image.url, headers=headers, image_indices=[i])
                        for i, image in enumerate(images))
    return info


def base(node, target, source, page):
    description = first(node, "desc", "description", "caption", "title")
    user = node.get("user") or node.get("author") or node.get("contact") or {}
    if not isinstance(user, dict):
        user = {}
    return VideoInfo(source, page, target, first(node, "title") or description.split("\n")[0] or f"{platform(source)}内容 {target}",
                     first(user, "nickname", "nickName", "name", "userName") or first(node, "userName", "nickName"),
                     number(node.get("duration")) / 1000, media_url(first(node, "coverUrl", "cover", "poster")),
                     platform(source) or platform(page), description=description)


def add_format(info, url, item=None, alternatives=None):
    item = item or {}
    candidates = list(dict.fromkeys(u for x in [url, *(alternatives or [])] if (u := media_url(x)) and not marked_url(u)))
    if not candidates or marked_metadata(item):
        return
    url = candidates[0]
    if any(f.url == url for f in info.formats) or item.get("drm") or item.get("hasDrm") or item.get("has_drm"):
        return
    width, height = number(item.get("width")), number(item.get("height"))
    fmt = VideoFormat(str(len(info.formats)), f"{width} × {height}" if width and height else "公开播放画质", url,
                      height=height, width=width, size=number(item.get("size")),
                      headers={"User-Agent": DESKTOP_UA, "Referer": info.page_url},
                      alternatives=candidates[1:])
    info.formats.append(fmt)


def douyin_album(node, target, source, page):
    info = base(node, target, source, page)
    info.platform = "抖音"
    images = node.get("images") or (node.get("image_post_info") or {}).get("images")
    if not images:
        return None
    selected = []
    for item in images:
        if isinstance(item, dict):
            variants = [item.get("origin_image"), item.get("original_image"), item, item.get("display_image")]
            clean = next((asset for variant in variants if (asset := image_asset(variant))), None)
            if clean is None:
                return None
            selected.append({"url": clean.url, "width": clean.width, "height": clean.height, "alternatives": clean.alternatives})
        else:
            selected.append(item)
    return album(info, selected)


def xhs_note(node, target, source, page):
    info = base(node, target, source, page)
    video = node.get("video") or {}
    if node.get("type") in ("normal", "image") or not video:
        return album(info, node.get("imageList"))
    for entries in ((video.get("media") or {}).get("stream") or {}).values():
        for entry in entries if isinstance(entries, list) else []:
            urls = [entry.get("masterUrl"), *(entry.get("backupUrls") or [])]
            urls = [x for x in urls if media_url(x)]
            if urls:
                add_format(info, urls[0], entry, urls[1:])
                info.duration = info.duration or number(entry.get("duration")) / 1000
    for key in ("url", "playUrl", "masterUrl"):
        add_format(info, video.get(key))
    info.formats.sort(key=lambda f: (f.height, f.size), reverse=True)
    return info if info.formats else None


def unpack(value, cache, active=None, depth=0):
    active = active or set()
    if depth > 20:
        return None
    if isinstance(value, dict):
        ref = value.get("__ref") or (value.get("id") if value.get("type") == "id" else "")
        if ref and ref in cache:
            return None if ref in active else unpack(cache[ref], cache, active | {ref}, depth + 1)
        return {k: unpack(v, cache, active, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [unpack(v, cache, active, depth + 1) for v in value]
    return value


def kuaishou_note(node, target, source, page):
    child = node.get("photo")
    if isinstance(child, dict):
        node = {**node, **child}
    info = base(node, target, source, page)
    extra = node.get("ext_params") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except ValueError:
            extra = {}
    atlas = node.get("atlas") or node.get("imageAtlas") or extra.get("atlas")
    if isinstance(atlas, str):
        try:
            atlas = json.loads(atlas)
        except ValueError:
            atlas = None
    items = node.get("images") or node.get("imgUrls")
    if isinstance(atlas, list):
        items = atlas
    elif isinstance(atlas, dict):
        items = atlas.get("list") or atlas.get("images")
        cdns = atlas.get("cdn") or atlas.get("cdnUrl") or atlas.get("cdnList") or []
        if not isinstance(cdns, list):
            cdns = [cdns]
        cdns = [x.get("cdn", "") if isinstance(x, dict) else x for x in cdns]
        cdns = [media_url(x if x.startswith(("http:", "https:", "//")) else "https://" + x).rstrip("/") + "/" for x in cdns if isinstance(x, str) and x]
        if items:
            items = [{"url": cdns[0] + x.lstrip("/"), "alternatives": [c + x.lstrip("/") for c in cdns[1:]]}
                     if isinstance(x, str) and not x.startswith(("http:", "https:", "//")) and cdns else x for x in items]
    if atlas or node.get("photoType") in (2, "ATLAS", "IMAGE") or node.get("type") in ("image", "atlas"):
        return album(info, items)
    for key in ("playUrl", "videoUrl", "url", "photoUrl", "photoH265Url"):
        add_format(info, node.get(key), node)
    for item in node.get("mainMvUrls") or []:
        add_format(info, item.get("url"), node)
    for part in (node.get("video"), node.get("videoResource"), node.get("manifest"), node.get("manifestH265")):
        for item in walk(part):
            if item.get("url") and any(k in item for k in ("width", "height", "qualityType")):
                value = item["url"]
                value = value.get("json") if isinstance(value, dict) else value
                for url in value if isinstance(value, list) else [value]:
                    add_format(info, url, item)
            add_format(info, item.get("playUrl"), item)
    info.formats.sort(key=lambda f: f.height, reverse=True)
    return info if info.formats else None


def channels_note(node, target, source, page):
    info = base(node, target, source, page)
    desc = node.get("objectDesc") or node.get("object_desc") or node
    items = desc.get("media") or desc.get("mediaList") or []
    if not items:
        return None
    info.description = first(desc, "description", "desc") or info.description
    if info.description:
        info.title = info.description.split("\n")[0]
    if all(x.get("mediaType", x.get("type")) in (2, "image") for x in items):
        return album(info, items)
    for item in items:
        if item.get("drm") or item.get("mediaType") == 9:
            return None
        url = first(item, "url", "videoUrl")
        token = item.get("urlToken") or ""
        if token.startswith(("?", "&")):
            url += token
        add_format(info, url, item)
        if info.formats and (key := str(item.get("decodeKey") or item.get("decode_key") or "")) not in ("", "0"):
            if not key.isdigit() or number(key) >= 2**64:
                return None
            info.formats[-1].decode_key = key
        info.duration = max(info.duration, number(item.get("videoPlayLen") or item.get("duration")))
    return info if info.formats else None


def from_payload(payload, target, source, page):
    if not target:
        return None
    name = platform(source) or platform(page)
    if name == "抖音":
        return video_from_payload(payload, target, source, page)
    if name == "视频号" and isinstance(payload, dict):
        context, feed = payload.get("previewPage", ""), payload.get("feedInfo")
        author = payload.get("authorInfo") or {}
        request = payload.get("requestUrl", "")
        if not context and host(request, "channels.weixin.qq.com") and urlsplit(request).path == "/finder-preview/api/feed/get_feed_info":
            context = parse_qs(urlsplit(request).query).get("_pageUrl", [""])[0]
            response = payload.get("response") or {}
            if response.get("errCode") == 0:
                feed = (response.get("data") or {}).get("feedInfo")
                author = (response.get("data") or {}).get("authorInfo") or {}
        if context and content_id(context) == target and platform(context) == platform(page) and urlsplit(context).path == "/finder-preview/pages/sph" and feed and not feed.get("drm"):
            info = base(feed, target, source, page)
            info.author = first(author, "nickname", "nickName")
            if feed.get("picInfo"):
                return album(info, feed["picInfo"])
            for key in ("h264VideoInfo", "h265VideoInfo"):
                item = feed.get(key) or {}
                add_format(info, item.get("videoUrl"), item)
            add_format(info, feed.get("videoUrl"), feed)
            if info.formats:
                return info
    for node in walk(payload):
        if node.get("drm") or node.get("hasDrm"):
            continue
        if name == "快手":
            cache = node.get("defaultClient") or {}
            if isinstance(cache, dict) and f"VisionVideoDetailPhoto:{target}" in cache:
                photo = unpack(cache[f"VisionVideoDetailPhoto:{target}"], cache)
                if not isinstance(photo, dict) or photo.get("photoId") not in (None, "", target):
                    continue
                result = kuaishou_note({**photo, "photoId": target}, target, source, page)
                if result:
                    return result
        keys = ("noteId", "note_id", "id") if name == "小红书" else ("photoId", "photo_id", "objectId", "object_id", "feedId", "id", "encryptedObjectId")
        matches = any(str(node.get(k, "")) == target for k in keys)
        if name == "快手" and not matches:
            actual = first(node, "photoId", "photo_id", "id")
            alias = parse_qs(node.get("share_info") or "").get("photoId", [""])[0]
            numeric = parse_qs(urlsplit(page).query).get("shareObjectId", [""])[0]
            matches = bool(actual and alias == target == content_id(page) and (not numeric or actual == numeric))
        if matches:
            parser = {"小红书": xhs_note, "快手": kuaishou_note, "视频号": channels_note}.get(name)
            result = parser(node, target, source, page) if parser else None
            if result:
                return result
        if name == "B站" and target.startswith("opus") and str(node.get("id_str") or node.get("id")) == target[4:]:
            modules = node.get("modules") or {}
            dynamic = modules.get("module_dynamic") or {}
            major = dynamic.get("major") or {}
            opus = major.get("opus") or {}
            draw = major.get("draw") or {}
            description = (dynamic.get("desc") or {}).get("text") or (opus.get("summary") or {}).get("text") or ""
            info = VideoInfo(source, page, target, opus.get("title") or f"B站图文 {target}",
                             (modules.get("module_author") or {}).get("name", ""), platform="B站", description=description)
            return album(info, draw.get("items") or opus.get("pics"))
    return None


def from_html(body, target, source, page):
    if platform(source) == "B站" and target.startswith("cv") and content_id(page) == target:
        section = re.search(r'article-holder(.*?)(?:article-footer|$)', body, re.S)
        if section:
            urls = []
            for figure in re.findall(r"<figure\b[^>]*>(.*?)</figure>", section[1], re.S | re.I):
                tag = re.search(r'<img\b([^>]*)>', figure, re.I)
                match = re.search(r'data-src=["\x27]([^"\x27]+)', tag[1], re.I) if tag else None
                if tag and not match:
                    match = re.search(r'(?:^|\s)src=["\x27]([^"\x27]+)', tag[1], re.I)
                if match and match[1] not in urls:
                    urls.append(match[1])
            title = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
            return album(VideoInfo(source, page, target, html.unescape(title[1]) if title else f"B站专栏 {target}", platform="B站"), urls)
    payloads = script_payloads(body)
    if platform(source) == "B站" and target.startswith(("BV", "av")) and content_id(page) == target:
        metadata = next((node for payload in payloads for node in walk(payload)
                         if target in (node.get("bvid"), "av" + str(node.get("aid"))) and node.get("title")), None)
        play = next((node for payload in payloads for node in walk(payload) if node.get("dash") or node.get("durl")), None)
        if metadata and play:
            info = VideoInfo(source, page, metadata.get("bvid") or target, metadata["title"],
                             (metadata.get("owner") or {}).get("name", ""), metadata.get("duration", 0), platform="B站", description=metadata.get("desc", ""))
            bili_formats(info, play)
            if info.formats:
                return info
    for payload in payloads:
        result = from_payload(payload, target, source, page)
        if result:
            return result
    return None


class SocialResolver:
    def __init__(self, data_dir, log, cancel):
        self.data_dir, self.log, self.cancel = data_dir, log, cancel

    def resolve(self, source, interactive=False):
        name = platform(source)
        if name == "视频号" and host(source, "weixin.qq.com"):
            return self.channels(source)
        if interactive:
            return self.browser(source)
        with make_session(self.data_dir / "browser-state.json") as session:
            for agent in (DESKTOP_UA, MOBILE_UA):
                check_cancel(self.cancel)
                response = session.get(source, headers={"User-Agent": agent}, timeout=(12, 18))
                response.raise_for_status()
                if platform(response.url) != name:
                    raise AppError("分享链接跳转到了其他网站，请检查原链接。")
                page = response.url
                target = content_id(source) or content_id(page)
                if name == "B站" and target.startswith(("BV", "av")):
                    result = bili_video(session, target, source, page, self.cancel)
                elif name == "B站" and target.startswith("opus"):
                    api = session.get("https://api.bilibili.com/x/polymer/web-dynamic/v1/detail", params={"id": target[4:]},
                                      headers={"Referer": "https://www.bilibili.com/"}, timeout=(12, 18))
                    api.raise_for_status()
                    result = from_payload(api.json(), target, source, page)
                else:
                    result = from_html(response.text, target, source, page)
                if result:
                    return result
        raise AppError(f"{name}未提供完整内容。可使用「浏览器辅助解析」，完成登录或验证后读取目标内容。")

    def channels(self, source):
        if not re.fullmatch(r"/sph/[A-Za-z0-9]{1,128}/?", urlsplit(source).path) or not host(source, "weixin.qq.com"):
            raise AppError("请使用完整的视频号 sph 分享链接。")
        self.log("正在通过与安卓版相同的在线服务解析视频号公开链接…")
        # This public endpoint takes only the pasted share URL, never local cookies.
        response = requests.post("https://v.mtotech.com/api/resolve", json={"url": source},
                                 headers={"User-Agent": DESKTOP_UA, "Referer": "https://v.mtotech.com/"}, timeout=(12, 45))
        response.raise_for_status()
        check_cancel(self.cancel)
        payload = response.json()
        data = payload.get("data") or {}
        if not payload.get("ok") or data.get("drm") or data.get("media_type", 4) != 4:
            raise AppError("视频号服务未返回完整视频，请稍后重试。")
        info = base(data, content_id(source), source, source)
        info.author = data.get("author") or ""
        info.duration = data.get("duration") or 0
        for key in ("h264_url", "h265_url"):
            url = data.get(key) or ""
            if urlsplit(url).scheme == "https" and any(host(url, d) for d in ("finder.video.qq.com", "video.weixin.qq.com", "wxapp.tc.qq.com")) and url != data.get("cover_url"):
                add_format(info, url)
        if not info.formats:
            raise AppError("视频号服务没有返回可保存的完整视频。")
        return info

    def browser(self, source):
        from playwright.sync_api import sync_playwright, Error as BrowserError
        target, name = content_id(source), platform(source)
        self.log("请在独立浏览器打开目标内容，手动完成登录或验证。等待最多 3 分钟。")
        with sync_playwright() as p:
            context = None
            for channel in ("msedge", "chrome", None):
                try:
                    context = p.chromium.launch_persistent_context(str(self.data_dir / "browser-profile"),
                        channel=channel, headless=False, viewport={"width": 1280, "height": 840}, locale="zh-CN")
                    break
                except BrowserError:
                    pass
            if context is None:
                raise AppError("无法启动浏览器，请安装 Edge 或 Chrome。")
            page = context.pages[0] if context.pages else context.new_page()
            candidate = [None]

            def response_received(response):
                if not target or platform(response.url) != name or "json" not in response.headers.get("content-type", ""):
                    return
                try:
                    if number(response.headers.get("content-length")) < 5_000_000:
                        candidate[0] = from_payload(response.json(), target, source, page.url) or candidate[0]
                except Exception:
                    pass

            page.on("response", response_received)
            try:
                try:
                    page.goto(source, wait_until="domcontentloaded", timeout=30000)
                except BrowserError:
                    pass
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    check_cancel(self.cancel)
                    if page.is_closed():
                        raise AppError("浏览器已关闭。")
                    if platform(page.url) == name:
                        current = content_id(page.url)
                        target = target or current
                        if current == target and target:
                            result = candidate[0] or from_html(page.content(), target, source, page.url)
                            if result:
                                context.storage_state(path=str(self.data_dir / "browser-state.json"))
                                return result
                    page.wait_for_timeout(600)
                raise AppError("没有读取到目标内容的完整媒体。请检查登录、验证码或访问限制。")
            finally:
                context.close()


def bili_video(session, target, source, page, cancel):
    """Preserve the requested part and combine Bilibili's paired DASH streams."""
    headers = {"Referer": "https://www.bilibili.com/", "User-Agent": DESKTOP_UA}

    def get(path, params):
        check_cancel(cancel)
        response = session.get("https://api.bilibili.com" + path, params=params, headers=headers, timeout=(12, 18))
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", -1) != 0:
            raise AppError("B站需要登录或验证，请使用浏览器辅助解析。")
        return payload.get("data") or {}

    meta = get("/x/web-interface/view", {"bvid": target} if target.startswith("BV") else {"aid": target[2:]})
    if target not in (meta.get("bvid"), "av" + str(meta.get("aid"))):
        raise AppError("B站返回的内容编号与链接不一致。")
    index = number(parse_qs(urlsplit(source).query).get("p", parse_qs(urlsplit(page).query).get("p", ["1"]))[0])
    pages = meta.get("pages") or []
    if not 1 <= index <= len(pages):
        raise AppError("所选 B站分 P 不存在。")
    part = pages[index-1]
    canonical = f"https://www.bilibili.com/video/{meta['bvid']}?p={index}"
    info = VideoInfo(source, canonical, meta["bvid"], meta.get("title") or target,
                     (meta.get("owner") or {}).get("name", ""), part.get("duration") or meta.get("duration") or 0,
                     media_url(meta.get("pic")), "B站", description=meta.get("desc") or "")
    if len(pages) > 1:
        info.title += f" · P{index} {part.get('part', '')}"
    for options in ({"qn": 64, "fnval": 16, "fnver": 0, "fourk": 0}, {"qn": 32, "fnval": 1, "platform": "html5"}):
        data = get("/x/player/playurl", {"bvid": meta["bvid"], "cid": part["cid"], **options})
        bili_formats(info, data)
    if not info.formats:
        raise AppError("B站未提供完整音视频，受保护或试看内容不支持保存。")
    info.formats.sort(key=lambda f: f.height, reverse=True)
    return info


def bili_formats(info, data):
    if data.get("is_preview") or data.get("is_drm") or data.get("drm_tech_type"):
        return
    dash = data.get("dash") or {}
    audio = [a for a in dash.get("audio") or [] if str(a.get("codecs", "")).startswith("mp4a") and not a.get("drm")]
    sound = max(audio, key=lambda a: number(a.get("bandwidth"))) if audio else None

    def asset(item, kind):
        url = media_url(item.get("baseUrl") or item.get("base_url") or item.get("url"))
        return {"url": url, "kind": kind, "alternatives": item.get("backupUrl") or item.get("backup_url") or []} if url else None

    if sound:
        for video in dash.get("video") or []:
            if not str(video.get("codecs", "")).startswith("avc1") or video.get("drm"):
                continue
            picture, voice = asset(video, "video"), asset(sound, "audio")
            if picture and voice and not any(f.url == picture["url"] for f in info.formats):
                add_format(info, picture["url"], video)
                info.formats[-1].mode = "dash"
                info.formats[-1].assets = [picture, voice]
                info.formats[-1].label += " · 含声音"
    durl = data.get("durl") or []
    if durl and not str(data.get("format", "")).startswith("flv"):
        assets = [asset(x, "video") for x in durl]
        if all(assets) and not any(f.url == assets[0]["url"] for f in info.formats):
            add_format(info, assets[0]["url"], {"height": {80: 1080, 64: 720, 32: 480}.get(data.get("quality"), 360)}, assets[0]["alternatives"])
            info.formats[-1].label = "完整 MP4 · 含声音"
            if len(assets) > 1:
                info.formats[-1].mode, info.formats[-1].assets = "concat", assets
