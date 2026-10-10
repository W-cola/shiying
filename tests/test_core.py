import json
from pathlib import Path
from urllib.parse import quote

import pytest

from clipharbor.douyin import script_payloads, video_from_payload
from clipharbor.links import douyin_id, extract_links, is_douyin, safe_filename
from clipharbor.models import AppError


def test_share_text_and_canonical_id():
    text = "0.76 07/21 yGv:/ u@F.uF :8pm https://v.douyin.com/78nnhuQHT8k/ 复制此链接，打开Dou音搜索，直接观看视频！"
    assert extract_links(text) == ["https://v.douyin.com/78nnhuQHT8k/"]
    assert douyin_id("https://www.douyin.com/video/7693840282563565674?previous_page=web_code_link") == "7693840282563565674"
    assert douyin_id("https://www.douyin.com/?modal_id=123456789") == "123456789"


def test_host_detection_does_not_confuse_lookalikes():
    assert is_douyin("https://v.douyin.com/a/")
    assert is_douyin("https://www.iesdouyin.com/share/video/123/")
    assert not is_douyin("https://douyin.com.example.org/video/123")


@pytest.mark.parametrize("text", ["没有链接", "file:///C:/Windows/x", "https://user:password@example.org/a"])
def test_invalid_input(text):
    with pytest.raises(AppError):
        extract_links(text)


def test_windows_safe_names():
    assert safe_filename("CON", "123").startswith("_CON")
    name = safe_filename('../../标题: "视频"<>|?*', "../../123")
    assert not any(c in name for c in '/\\:"<>|?*')
    assert "[123]" in name


def test_decode_render_data_and_router_data():
    payload = {"aweme_id": "123", "desc": "真实视频", "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}}}
    page = '<script id="RENDER_DATA" type="application/json">' + quote(json.dumps(payload)) + '</script>'
    assert script_payloads(page) == [payload]
    assert script_payloads('<script>window._ROUTER_DATA = ' + json.dumps(payload) + ';</script>') == [payload]


def test_target_video_selected_over_recommendations_and_quality_sorted():
    def item(video_id, height):
        return {"aweme_id": video_id, "desc": "视频 " + video_id, "author": {"nickname": "作者"},
                "video": {"duration": 12300, "height": height, "width": 720,
                          "play_addr": {"url_list": [f"https://cdn.example/{video_id}.mp4"]},
                          "bit_rate": [{"gear_name": "高清", "play_addr": {"height": 1920, "width": 1080,
                                                                      "url_list": [f"https://cdn.example/{video_id}-hd.mp4"]}}]}}
    payload = {"recommendations": [item("999", 720)], "detail": item("123", 1280)}
    info = video_from_payload(payload, "123", "https://v.douyin.com/a", "https://www.douyin.com/video/123")
    assert info.video_id == "123"
    assert info.title == "视频 123"
    assert info.author == "作者"
    assert info.duration == 12.3
    assert info.formats[0].height == 1920
    assert all("123" in f.url for f in info.formats)
    assert video_from_payload(payload, "456", "", "") is None
