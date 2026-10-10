"""Exercise real grouped history and native image swipes through the preview page."""
import json
import re
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
from preview_server import adb

root=Path(__file__).resolve().parents[2]; report=root/'android/verification'; base='http://127.0.0.1:8787'; checks=0
def check(value,message):
    global checks
    assert value,message
    checks+=1
def nodes():
    output=adb('shell','uiautomator','dump','/sdcard/shiying-album-preview.xml')
    if b'dumped' not in output: raise RuntimeError(output.decode('utf-8','replace'))
    return list(ET.fromstring(adb('exec-out','cat','/sdcard/shiying-album-preview.xml')).iter('node'))
def click(page,label):
    control=next((n for n in nodes() if n.attrib.get('text')==label),None); check(control is not None,'Native control exists: '+label)
    x1,y1,x2,y2=map(int,re.findall(r'\d+',control.attrib['bounds'])); data=requests.get(base+'/screen',timeout=15).content; width,height=struct.unpack('>II',data[16:24]); box=page.locator('#screen').bounding_box()
    page.mouse.click(box['x']+box['width']*(x1+x2)/2/width,box['y']+box['height']*(y1+y2)/2/height)
def wait_label(value):
    deadline=time.monotonic()+50
    while time.monotonic()<deadline:
        tree=nodes()
        if any(n.attrib.get('text')==value for n in tree): return tree
        time.sleep(.2)
    raise AssertionError('Native text not found: '+value)
def swipe(page,left):
    box=page.locator('#screen').bounding_box(); page.mouse.move(box['x']+box['width']*(.8 if left else .2),box['y']+box['height']*.5); page.mouse.down(); page.mouse.move(box['x']+box['width']*(.2 if left else .8),box['y']+box['height']*.5,steps=12); page.mouse.up()
errors=[]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel='msedge',headless=True); page=browser.new_page(viewport={'width':960,'height':940}); page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='domcontentloaded')
    with page.expect_response(lambda response:response.url.endswith('/connect')) as response: page.locator('#connect').click()
    check(response.value.status==200,'Preview reconnect accepted')
    deadline=time.monotonic()+50
    while time.monotonic()<deadline:
        state=requests.get(base+'/state',timeout=5).json()
        if state['ready'] and not state['busy']: break
        time.sleep(.3)
    check(state['version']=='1.5.1' and state['ready'],'New APK installed in preview')
    page.wait_for_function('document.querySelector("#screen").naturalWidth > 0')
    click(page,'▦   我的片段'); time.sleep(.5)
    tree=nodes(); check(any('图文 · ' in n.attrib.get('text','') for n in tree),'Library displays grouped image collections')
    check(not any(re.search(r' · 图片 \d+/\d+$',n.attrib.get('text','')) for n in tree),'Each photo no longer appears as a separate library row')
    page.wait_for_timeout(900); page.screenshot(path=str(report/'album-library-v1.5.1.png'),full_page=True)
    page.locator('#launch').click(); page.locator('[data-sample="album"]').click(); page.locator('#send').click(); time.sleep(.5)
    click(page,'解析视频  →'); wait_label('▧  应用内预览'); click(page,'▧  应用内预览'); wait_label('1 / 10')
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        tree=nodes()
        if not any('正在加载' in n.attrib.get('text','') for n in tree): break
        time.sleep(.3)
    swipe(page,True); wait_label('2 / 10'); check(True,'Browser drag switches native picture to page two')
    time.sleep(1); page.screenshot(path=str(report/'album-swipe-v1.5.1.png'),full_page=True)
    (report/'album-native-preview-v1.5.1.png').write_bytes(adb('exec-out','screencap','-p'))
    swipe(page,False); wait_label('1 / 10'); check(True,'Opposite swipe returns to first picture')
    check('.ImageActivity' in adb('shell','dumpsys','activity','activities').decode('utf-8','replace'),'Pictures preview inside APK')
    page.locator('[data-key="back"]').click(); time.sleep(.5); click(page,'▦   我的片段'); time.sleep(.6)
    check(not errors,'No preview JavaScript errors'); browser.close()
result={'version':'1.5.1','checks':checks,'result':'passed','scope':'Real native grouped library and supplied Kuaishou album in browser preview; horizontal drag in both directions, ten-picture counter, no external viewer'}
(report/'album-preview-test-v1.5.1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result,ensure_ascii=False))
