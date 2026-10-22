import dataclasses
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event

import pytest

from clipharbor.channels_codec import ChannelsCodec
from clipharbor.douyin import script_payloads, video_from_payload
from clipharbor.engine import Engine
from clipharbor.media import ffmpeg, run_ffmpeg
from clipharbor.models import AppError, Cancelled, SavedMedia, VideoFormat, VideoInfo
from clipharbor.platforms import album, bili_formats, content_id, from_html, from_payload, platform
from clipharbor.store import Store


def test_note_ids_and_lookalike_hosts():
    assert content_id('https://www.douyin.com/note/123') == '123'
    assert content_id('https://www.xiaohongshu.com/explore/' + 'a'*24) == 'a'*24
    assert content_id('https://www.bilibili.com/opus/123') == 'opus123'
    assert content_id('https://www.bilibili.com/read/cv123') == 'cv123'
    assert platform('https://kuaishou.com.example.com/photo/123') == ''


def test_douyin_album_target_and_order():
    payload = [{'aweme_id': '999', 'images': [{'url_list': ['https://cdn.example/wrong.jpg']}]},
               {'aweme_id': '123', 'desc': '图文正文', 'images': [{'url_list': [f'https://cdn.example/{i}.jpg']} for i in range(3)]}]
    info = video_from_payload(payload, '123', 'https://www.douyin.com/note/123', 'https://www.douyin.com/note/123')
    assert info.kind == 'images' and len(info.images) == 3
    assert [x.url for x in info.images] == [f'https://cdn.example/{i}.jpg' for i in range(3)]
    assert info.formats[0].image_indices == [0, 1, 2]
    assert info.formats[2].image_indices == [1]
    assert video_from_payload(payload, '456', info.source_url, info.page_url) is None


def test_xhs_state_undefined_and_target_video():
    target = 'a'*24
    note = {'noteId': target, 'type': 'normal', 'desc': '正文', 'imageList': [{'urlDefault': 'https://cdn.example/1.jpg'}]}
    source = 'https://www.xiaohongshu.com/explore/' + target
    html = '<script>window.__INITIAL_STATE__=' + json.dumps({'note': note})[:-1] + ',"optional":undefined,"literal":"undefined"};</script>'
    payload = script_payloads(html)[0]
    assert payload['literal'] == 'undefined' and payload['optional'] is None
    assert from_payload(payload, target, source, source).description == '正文'
    assert from_payload(payload, 'b'*24, source, source) is None
    video = {**note, 'type': 'video', 'video': {'media': {'stream': {'h264': [{'masterUrl': 'https://cdn.example/v.mp4', 'width': 1080, 'height': 1920, 'duration': 15000}]}}}}
    info = from_payload(video, target, source, source)
    assert info.kind == 'video' and info.duration == 15 and info.formats[0].height == 1920


def test_kuaishou_apollo_and_atlas():
    source = 'https://www.kuaishou.com/short-video/test123'
    payload = {'defaultClient': {'VisionVideoDetailPhoto:test123': {'photoId': 'test123', 'caption': '组图',
                  'atlas': {'cdn': ['https://cdn.example/', 'https://backup.example/'], 'list': ['1.jpg', '2.jpg']}}}}
    info = from_payload(payload, 'test123', source, source)
    assert info.kind == 'images' and len(info.images) == 2
    assert info.images[1].url == 'https://cdn.example/2.jpg'
    assert info.images[0].alternatives == ['https://backup.example/1.jpg']
    assert from_payload(payload, 'wrong', source, source) is None
    payload['defaultClient']['VisionVideoDetailPhoto:test123']['photoId'] = 'wrong'
    assert from_payload(payload, 'test123', source, source) is None


def test_bilibili_article_prefers_real_image_over_placeholder():
    source = 'https://www.bilibili.com/read/cv123'
    body = "<title>正文</title><div class='article-holder'><figure><img src='data:blank' data-src='https://i0.hdslb.com/body.jpg'></figure></div>article-footer"
    info = from_html(body, 'cv123', source, source)
    assert info.images[0].url == 'https://i0.hdslb.com/body.jpg'


def test_bilibili_paired_dash_and_protected_preview_rejected():
    info = VideoInfo('', 'https://www.bilibili.com/video/BV1GJ411x7h7', 'BV1GJ411x7h7', '测试', platform='B站')
    data = {'dash': {'audio': [{'baseUrl': 'https://cdn.example/a.m4s', 'codecs': 'mp4a.40.2', 'bandwidth': 100}],
                     'video': [{'baseUrl': 'https://cdn.example/v.m4s', 'codecs': 'avc1.640028', 'width': 1920, 'height': 1080}]}}
    bili_formats(info, {**data, 'is_preview': 1})
    assert not info.formats
    bili_formats(info, {**data, 'is_drm': True})
    assert not info.formats
    bili_formats(info, data)
    assert info.formats[0].mode == 'dash'
    assert [x['kind'] for x in info.formats[0].assets] == ['video', 'audio']


@pytest.fixture
def picture_server():
    # A complete valid 1x1 PNG, independent of any external website.
    import base64
    image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            payload = b'<html>login</html>' if self.path == '/error.jpg' else image
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if self.path == '/error.jpg' else 'image/png')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join()


def test_album_atomic_saving_preview_and_batch_deletion(tmp_path, picture_server):
    store = Store(tmp_path / 'data')
    engine = Engine(store.root)
    info = album(VideoInfo('https://example.org/post', 'https://example.org/post?token=private', '123', '组图', '作者', platform='快手', description='正文内容'),
                 [picture_server + '/1.jpg', picture_server + '/2.jpg'])
    result = engine.download(info, info.formats[0], tmp_path / 'output')
    assert result.kind == 'images' and len(result.files) == 3
    assert [x.name for x in result.files] == ['001.png', '002.png', '正文.txt']
    assert '正文内容' in result.files[-1].read_text(encoding='utf-8')
    assert 'token=' not in result.files[-1].read_text(encoding='utf-8')
    store.add_history(info, result)
    second = engine.download(info, info.formats[1], tmp_path / 'output')
    store.add_history(info, second)
    assert len(store.records('images', '作者')) == 2
    preview = engine.prepare_preview(info, info.formats[0])
    assert preview.temporary and len(store.records()) == 2
    store.delete_record(store.records()[1])
    assert not result.path.exists() and second.path.exists()
    assert len(store.records()) == 1


def test_album_failure_leaves_no_partial_group(tmp_path, picture_server):
    engine = Engine(tmp_path / 'data')
    info = album(VideoInfo('', '', '123', '失败'), [picture_server+'/1.jpg', picture_server+'/error.jpg'])
    with pytest.raises(AppError):
        engine.download(info, info.formats[0], tmp_path/'output')
    assert not list((tmp_path/'output').iterdir())


def test_legacy_history_and_precise_delete(tmp_path):
    store = Store(tmp_path/'data')
    path = tmp_path/'legacy.mp4'
    path.write_bytes(b'test')
    store.write('history.json', [{'title': '旧记录', 'platform': '抖音', 'path': str(path), 'size': 4, 'time': '2026-10-01'}])
    assert len(store.records('video', '旧')) == 1
    store.delete_record(store.records()[0], delete_files=False)
    assert path.exists() and not store.records()


def test_codec_is_chunk_independent_and_prefix_limited():
    data = bytes(range(256))*600
    expected = ChannelsCodec('18446744073709551615').apply(data)
    codec = ChannelsCodec('18446744073709551615')
    actual = b''.join(codec.apply(data[i:i+997]) for i in range(0, len(data), 997))
    assert actual == expected
    assert actual[131072:] == data[131072:]
    assert ChannelsCodec('18446744073709551615').apply(actual) == data


@pytest.mark.parametrize('key,digest', [('0','e1662af3b7e59867c919ad19055fc8cecea2b154d37e1459b2f96d1da14cef1f'),
    ('123456789','1f972db9d304b9c779a59f9830f1b03c98e247a4e1102d926996dd61b60d8e67'),
    ('18446744073709551615','5afbffd76305e81467f97c6370fa07916e9b197611bf5c357a854eb92a6354a1')])
def test_codec_matches_android_reference_vectors(key, digest):
    import hashlib
    assert hashlib.sha256(ChannelsCodec(key).apply(bytes(131072))).hexdigest() == digest


@pytest.fixture
def video_sample(tmp_path):
    path = tmp_path/'sample.mp4'
    run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=15', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                '-t', '2', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', path], Event())
    return path


def audio_payload(path):
    return subprocess.check_output([ffmpeg(), '-v', 'error', '-i', str(path), '-map', '0:a:0', '-c:a', 'copy', '-f', 'adts', '-'],
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def test_actual_audio_extraction_keeps_aac_packets(tmp_path, video_sample):
    engine = Engine(tmp_path/'data')
    info = VideoInfo('', '', '123', '真实音轨')
    result = engine.extract_audio(info, None, tmp_path/'sound', video_sample)
    assert result.kind == 'audio' and result.path.suffix == '.m4a'
    assert audio_payload(result.path) == audio_payload(video_sample)
    # Full decode, not merely a file extension or container-header check.
    run_ffmpeg(['-i', result.path, '-f', 'null', '-'], Event())
    assert not list((engine.data_dir/'preview-cache').glob('preview-*'))


def test_no_audio_fails_without_empty_output(tmp_path):
    path = tmp_path/'silent.mp4'
    run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10', '-t', '0.3', '-an', '-c:v', 'libx264', path], Event())
    with pytest.raises(AppError):
        Engine(tmp_path/'data').extract_audio(VideoInfo('', '', '123', '无音轨'), None, tmp_path/'audio', path)
    assert not list((tmp_path/'audio').iterdir())


def test_cli_album_records_remain_grouped(tmp_path, picture_server):
    import os
    import sys
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, 'CLIPHARBOR_DATA': str(tmp_path/'data'), 'PYTHONIOENCODING': 'utf-8'}
    result = subprocess.run([sys.executable, str(root/'main.py'), '--url', picture_server+'/1.jpg', '--download',
                             '--output', str(tmp_path/'output'), '--report', str(tmp_path/'report.json')],
                            env=env, cwd=root, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    records = Store(tmp_path/'data').records()
    assert len(records) == 1 and records[0]['kind'] == 'images'
    assert len(records[0]['files']) == 2 and Path(records[0]['path']).is_dir()
