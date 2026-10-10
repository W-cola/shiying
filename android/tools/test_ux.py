"""Exercise the new native collection/sheets/audio player from the real preview browser."""
import json,re,struct,time,xml.etree.ElementTree as ET
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
from preview_server import adb

root=Path(__file__).resolve().parents[2]; report=root/'android/verification'; base='http://127.0.0.1:8787'; checks=0
version=json.loads((report/'build.json').read_text(encoding='utf-8'))['version']
def check(value,message):
    global checks
    assert value,message
    checks+=1
def nodes():
    for attempt in range(3):
        out=adb('shell','uiautomator','dump','/sdcard/shiying-ux.xml')
        if b'dumped' in out:return list(ET.fromstring(adb('exec-out','cat','/sdcard/shiying-ux.xml')).iter('node'))
        time.sleep(.5)
    raise AssertionError('Android hierarchy did not settle: '+out.decode('utf-8','replace'))
def bounds(node):return list(map(int,re.findall(r'\d+',node.attrib['bounds'])))
def click_node(page,node):
    x1,y1,x2,y2=bounds(node); frame=requests.get(base+'/screen',timeout=15).content; w,h=struct.unpack('>II',frame[16:24]); box=page.locator('#screen').bounding_box();page.mouse.click(box['x']+box['width']*(x1+x2)/2/w,box['y']+box['height']*(y1+y2)/2/h)
def tap(page,label):
    node=next((n for n in nodes() if n.attrib.get('text')==label),None);check(node is not None,'Visible native control: '+label);click_node(page,node);time.sleep(.35)
def wait_text(value,timeout=30):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        tree=nodes()
        if any(value in n.attrib.get('text','') for n in tree):return tree
        time.sleep(.2)
    raise AssertionError('Native result not found: '+value)
def shot(page,name):
    time.sleep(.6);page.screenshot(path=str(report/(name+'-v'+version+'.png')),full_page=True)
    (report/(name+'-native-v'+version+'.png')).write_bytes(adb('exec-out','screencap','-p'))
def find_rick(page):
    for _ in range(7):
        tree=nodes(); node=next((n for n in tree if 'Rick Astley' in n.attrib.get('text','') and not n.attrib.get('text','').endswith(' · 原声')),None)
        if node is not None:return node
        box=page.locator('#screen').bounding_box();page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.8);page.mouse.down();page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.4,steps=12);page.mouse.up();time.sleep(.3)
    raise AssertionError('Existing local Bili collection unavailable')
font=adb('shell','settings','get','system','font_scale').decode().strip()
old_files=set(adb('shell','ls','-1','/sdcard/Music/拾影').decode('utf-8','replace').splitlines())
errors=[]
try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':960,'height':940});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base,wait_until='domcontentloaded');page.wait_for_function('document.querySelector("#screen").naturalWidth>0')
        page.locator('#launch').click();time.sleep(.6)
        check(page.locator('#version').inner_text().endswith('v'+version),'Preview shows correct build')
        tap(page,'收下视频');shot(page,'ux-home')
        tap(page,'我的片段');tap(page,'视频');check(not any('图文 · ' in n.attrib.get('text','') for n in nodes()),'Video filter excludes image groups')
        click_node(page,find_rick(page));wait_text('提取原声音频');tree=nodes()
        check(any(n.attrib.get('text')=='分享视频' for n in tree),'Detail sheet provides share')
        check(any('相册 · 拾影' in n.attrib.get('text','') for n in tree),'Sheet shows real save location')
        play=next(n for n in tree if n.attrib.get('clickable')=='true' and '播放视频' in n.attrib.get('content-desc',''))
        x1,y1,x2,y2=bounds(play);check(y2-y1>=126,'Main sheet action has at least 48dp touch height')
        shot(page,'ux-video-sheet');tap(page,'关闭');check(not any(n.attrib.get('text')=='分享视频' for n in nodes()),'Close dismisses only the sheet')
        # Search through the actual phone keyboard and retain state after font recreation.
        search=next(n for n in nodes() if n.attrib.get('class')=='android.widget.EditText');click_node(page,search);adb('shell','input','text','Rick');adb('shell','input','keyevent','4');time.sleep(.4)
        tree=nodes();check(any(n.attrib.get('text')=='Rick' for n in tree),'Library search input works')
        check(any('Rick Astley' in n.attrib.get('text','') for n in tree),'Search retains matching downloaded item')
        adb('shell','settings','put','system','font_scale','1.3');time.sleep(1)
        tree=nodes();check(any(n.attrib.get('text')=='Rick' for n in tree),'Search survives font-size recreation')
        check(any(n.attrib.get('text')=='视频' and n.attrib.get('selected')=='true' for n in tree),'Selected category survives recreation')
        click_node(page,find_rick(page));wait_text('提取原声音频');tree=nodes()
        frame=requests.get(base+'/screen',timeout=15).content;w,h=struct.unpack('>II',frame[16:24])
        check(all(0<=bounds(n)[0]<=bounds(n)[2]<=w and 0<=bounds(n)[1]<=bounds(n)[3]<=h for n in tree if n.attrib.get('text') in ('关闭','播放视频','分享视频')),'Large-font key actions stay in screen bounds')
        shot(page,'ux-large-font-sheet');tap(page,'关闭');adb('shell','settings','put','system','font_scale',font if font!='null' else '1.0');time.sleep(.8)
        search=next(n for n in nodes() if n.attrib.get('class')=='android.widget.EditText');click_node(page,search);adb('shell','input','keyevent','123');
        for _ in range(4):adb('shell','input','keyevent','67')
        adb('shell','input','keyevent','4');time.sleep(.3);tap(page,'全部');shot(page,'ux-library');tap(page,'视频');click_node(page,find_rick(page));wait_text('提取原声音频');tap(page,'提取原声音频')
        tap(page,'音频');tree=wait_text('原声 · M4A',60)
        until=time.monotonic()+60
        while not any('原声 · M4A' in n.attrib.get('text','') and '已保存' in n.attrib.get('text','') for n in tree):
            if time.monotonic()>until:raise AssertionError('Local sound extraction did not finish')
            time.sleep(.4);tree=nodes()
        check(not any('图文 · ' in n.attrib.get('text','') for n in tree),'Audio filter excludes albums')
        node=next(n for n in tree if n.attrib.get('text','').endswith(' · 原声'));click_node(page,node);wait_text('播放音频');check(any(n.attrib.get('text')=='分享音频' for n in nodes()),'Saved audio has independent share action');tap(page,'播放音频');time.sleep(1);adb('shell','input','keyevent','127');time.sleep(.4)
        check('.AudioActivity' in adb('shell','dumpsys','activity','activities').decode('utf-8','replace'),'Browser opens actual in-app audio player')
        check(any(n.attrib.get('text')=='播放' for n in nodes()),'Media-session pause button works')
        shot(page,'ux-audio-player');tap(page,'返回');tree=nodes();node=next(n for n in tree if n.attrib.get('text','').endswith(' · 原声'));click_node(page,node);wait_text('删除片段');tap(page,'删除片段');wait_text('删除文件');check(any(n.attrib.get('text')=='保留' for n in nodes()),'Deletion has explicit retain choice');shot(page,'ux-delete-sheet');tap(page,'保留');tree=nodes();node=next(n for n in tree if n.attrib.get('text','').endswith(' · 原声'));click_node(page,node);tap(page,'删除片段');tap(page,'删除文件');wait_text('还没有匹配的片段')
        check(set(adb('shell','ls','-1','/sdcard/Music/拾影').decode('utf-8','replace').splitlines())==old_files,'Only newly created test audio was removed')
        page.set_viewport_size({'width':390,'height':844});time.sleep(.5);check(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Narrow preview has no horizontal overflow');check(not errors,'No preview JavaScript errors')
        tap(page,'全部');browser.close()
finally:
    adb('shell','settings','put','system','font_scale',font if font!='null' else '1.0')
result={'version':version,'checks':checks,'result':'passed','scope':'Real native sheets, search/filter/recreation, 130% font, audio extract/play/pause/delete through local browser; only a test audio created and deleted'}
(report/('ux-preview-test-v'+version+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
