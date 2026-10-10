"""Offline browser fixtures for the scripts shipped inside the Android WebView.

Requires the development-only playwright package and an installed Edge browser.
All page and fetch/XHR responses are locally fulfilled; no live site is tested.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[2]
assets = root / 'android/app/src/main/assets'
capture = (assets / 'browser_capture.js').read_text(encoding='utf-8')
reader = (assets / 'browser_read.js').read_text(encoding='utf-8')
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context()
    payload = {'target': 'fixture', 'video': {'url': 'https://media.example.test/sample.mp4'}}

    def respond(route):
        if route.request.resource_type == 'document':
            route.fulfill(status=200, content_type='text/html', body='<title>Fixture</title><video style="width:320px;height:180px"></video>')
        else:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))

    context.route('**/*', respond)
    page = context.new_page()
    for site, endpoint in [
        ('https://www.douyin.com/video/123', 'https://www.douyin.com/aweme/v1/web/aweme/detail/'),
        ('https://www.bilibili.com/video/BV1GJ411x7h7', 'https://api.bilibili.com/x/player/playurl?bvid=BV1GJ411x7h7&cid=1'),
        ('https://www.kuaishou.com/short-video/fixture', 'https://www.kuaishou.com/graphql'),
        ('https://v.m.chenzhongtech.com/fw/photo/fixture', 'https://v.m.chenzhongtech.com/rest/photo/detail'),
        ('https://channels.weixin.qq.com/feed/fixture', 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/interaction'),
    ]:
        page.goto(site)
        page.evaluate(capture)
        fetch_result = page.evaluate('async u => (await fetch(u)).json()', endpoint)
        check(fetch_result == payload, 'Capture must preserve the original fetch response')
        page.wait_for_function('window.__shiyingPayloads.length === 1')
        xhr_result = page.evaluate('u => new Promise(resolve => { const x = new XMLHttpRequest(); x.open("GET",u); x.responseType="json"; x.onload=()=>resolve(x.response); x.send(); })', endpoint)
        check(xhr_result == payload, 'Capture must preserve the original XHR response')
        captured = page.evaluate('window.__shiyingPayloads')
        check(len(captured) == 2 and all(item['requestUrl'] == endpoint for item in captured), 'Capture includes request provenance')
        read = json.loads(page.evaluate(reader))
        check(any(json.loads(p).get('response') == payload for p in read['payloads']), 'Reader forwards published JSON to the native target parser')

    page.goto('https://www.bilibili.com/video/BV1GJ411x7h7?p=2')
    page.evaluate(capture)
    page.evaluate('window.__INITIAL_STATE__={videoData:{bvid:"BV1GJ411x7h7",title:"Fixture",pages:[{page:2,cid:1}]}};window.__playinfo__={code:0,data:{cid:1,dash:{video:[],audio:[]}}};')
    read = json.loads(page.evaluate(reader))
    bound = [json.loads(p) for p in read['payloads'] if 'biliPage' in json.loads(p)]
    check(len(bound) == 1 and bound[0]['biliPage'].endswith('?p=2'), 'Bilibili page, metadata and playback are kept together')
    page.evaluate('async () => { for(let i=0;i<15;i++) await fetch("https://api.bilibili.com/x/web-interface/view?aid="+i); }')
    page.wait_for_function('window.__shiyingPayloads.length === 12')
    check(page.evaluate('window.__shiyingPayloads.length') == 12, 'Captured response queue is bounded')
    page.evaluate('async () => (await fetch("https://api.bilibili.com.example.test/x/player/playurl")).json()')
    check(page.evaluate('window.__shiyingPayloads.length') == 12, 'Lookalike domains are excluded')
    check(all('example.test' not in p['requestUrl'] for p in page.evaluate('window.__shiyingPayloads')), 'Untrusted capture did not enter the queue')

    page.goto('https://www.xiaohongshu.com/explore/fixture')
    page.evaluate('window.__INITIAL_STATE__={note:{noteId:"fixture",imageList:[{urlDefault:"https://media.example.test/picture.jpg"}]}}')
    read = json.loads(page.evaluate(reader))
    check(json.loads(read['payloads'][0])['note']['noteId'] == 'fixture', 'Existing Xiaohongshu global-state reading is preserved')
    page.goto('https://channels.weixin.qq.com/feed/fixture')
    page.evaluate('''() => {
      const video=document.querySelector('video');
      video.__reactFiber$fixture={memoizedProps:{account:{secret:'secret-marker'},feed:{id:'fixture',objectDesc:{media:[{type:4,url:'https://media.example.test/v.mp4'}]}}}};
      Object.defineProperty(video,'duration',{value:Infinity});
    }''')
    read = json.loads(page.evaluate(reader))
    check(read['duration'] == 0, 'Unknown duration stays a valid JSON number')
    check(any(json.loads(p).get('id') == 'fixture' for p in read['payloads']), 'Active media props are readable when no global is published')
    check('secret-marker' not in ''.join(read['payloads']), 'Account props are skipped')
    page.goto('https://channels.weixin.qq.com/finder-preview/pages/sph?id=fixture')
    page.evaluate('''() => {
      const app=document.createElement('div');app.id='app';document.body.appendChild(app);
      app.__vue_app__={config:{globalProperties:{$pinia:{state:{value:{feed:{feed:{description:'Fixture',coverUrl:'https://qpic.cn/cover.jpg',picInfo:[]},finderAcct:{nickname:'Author'}}}}}}}};
    }''')
    read = json.loads(page.evaluate(reader))
    check('没有提供可下载的视频地址' in read.get('platformMessage', ''), 'Preview-only pages give a clear explanation')
    check(any(json.loads(p).get('previewPage', '').endswith('id=fixture') for p in read['payloads']), 'Only the published Vue feed DTO is captured with page provenance')
    page.evaluate("document.querySelector('#app').__vue_app__.config.globalProperties.$pinia.state.value.feed.feed.h264VideoInfo={videoUrl:'https://finder.video.qq.com/v.mp4'}")
    read = json.loads(page.evaluate(reader))
    check('platformMessage' not in read, 'Normal published video does not receive preview-only warning')
    browser.close()

report = {'version': '1.5.0', 'checks': checks, 'result': 'passed',
          'scope': 'offline routed browser fixtures; not a live-platform success claim'}
(root / 'android/verification/browser-assets-test-v1.4.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
