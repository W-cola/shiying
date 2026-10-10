"""Test the local preview bridge and actual APK interactions from an isolated browser."""
import json
import re
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
from preview_server import adb

root=Path(__file__).resolve().parents[2]
report=root/'android/verification'
version=json.loads((report/'build.json').read_text(encoding='utf-8'))['version']
url='http://127.0.0.1:8787'
checks=0

def check(value,message):
    global checks
    assert value,message
    checks+=1

def nodes():
    output=adb('shell','uiautomator','dump','/sdcard/shiying-preview-qa.xml')
    if b'dumped' not in output: raise RuntimeError('Android hierarchy is not idle: '+output.decode('utf-8','replace'))
    return list(ET.fromstring(adb('exec-out','cat','/sdcard/shiying-preview-qa.xml')).iter('node'))

def click_fraction(page,x,y):
    box=page.locator('#screen').bounding_box()
    page.mouse.click(box['x']+box['width']*x,box['y']+box['height']*y)

def playing():
    value=adb('shell','dumpsys','media.player').decode('utf-8','replace').split('Decoder infos')[0]
    frames=re.search(r'numFramesTotal\((\d+)\)',value)
    return 'packageName: cn.shiying.mobile' in value and 'renderer(paused(0)' in value and frames is not None and int(frames.group(1))>0

def tap(page,label):
    tree=nodes()
    control=next((n for n in tree if n.attrib.get('text')==label),None)
    check(control is not None,'Native button exists: '+label)
    x1,y1,x2,y2=map(int,re.findall(r'\d+',control.attrib['bounds']))
    frame=requests.get(url+'/screen',timeout=15).content
    width,height=struct.unpack('>II',frame[16:24])
    x,y=(x1+x2)/2/width,(y1+y2)/2/height
    click_fraction(page,x,y)
    return x,y

deadline=time.monotonic()+50
while not requests.get(url+'/state',timeout=5).json()['ready']:
    if time.monotonic()>deadline: raise AssertionError('Preview did not become ready')
    time.sleep(.5)
page_html=requests.get(url+'/',timeout=5).text
token=re.search(r"const token='([^']+)'",page_html).group(1)
headers={'Origin':url,'X-Preview-Token':token}
check(requests.post(url+'/key',json={'key':'home'},timeout=5).status_code==403,'Unauthenticated input rejected')
check(requests.post(url+'/key',headers={**headers,'Origin':'https://example.com'},json={'key':'home'},timeout=5).status_code==403,'Cross-site input rejected')
check(requests.get(url+'/../../.android-build/private/signing-password.txt',timeout=5).status_code==404,'No arbitrary filesystem serving')
check(requests.get(url+'/state',headers={'Host':'example.com'},timeout=5).status_code==403,'Unrelated Host rejected')
check(requests.post(url+'/share',headers=headers,json={'text':' '},timeout=5).status_code==400,'Empty share rejected')
errors=[]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':960,'height':940},device_scale_factor=1)
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url,wait_until='domcontentloaded')
    page.wait_for_function('document.querySelector("#screen").naturalWidth > 0')
    check(page.title()=='拾影 · 安卓实时预览','Preview page loads')
    check(page.locator('#version').inner_text().endswith('v'+version),'Installed version shown')
    page.locator('[data-key="home"]').click(); time.sleep(.6)
    page.locator('#launch').click(); time.sleep(.8)
    page.locator('[data-sample="douyin"]').click()
    check('xP--46iFdBs' in page.locator('#share').input_value(),'Sample fills real supplied link')
    page.locator('#send').click(); time.sleep(.7)
    check(any('xP--46iFdBs' in n.attrib.get('text','') for n in nodes()),'Chinese whole-share text reaches native APK')
    tap(page,'解析视频  →')
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        tree=nodes()
        if any(n.attrib.get('text')=='▶  应用内播放' for n in tree): break
        time.sleep(.5)
    else: raise AssertionError('Native share resolution did not finish')
    check(any('发布会' in n.attrib.get('text','') for n in tree),'Actual share resolves in APK')
    time.sleep(1)
    page.screenshot(path=str(report/('preview-home-v'+version+'.png')),full_page=True)
    tap(page,'▶  应用内播放')
    deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        if playing(): break
        time.sleep(.2)
    else: raise AssertionError('Native video did not decode in preview')
    check('cn.shiying.mobile/.PlayerActivity' in adb('shell','dumpsys','activity','activities').decode('utf-8','replace'),'Actual APK player is foreground')
    # Changing elapsed text prevents uiautomator's idle wait during playback.
    # Pause with a real screen touch first, then inspect the stable controls.
    click_fraction(page,.5,.5); time.sleep(.4)
    check(any(n.attrib.get('text')=='播放' for n in nodes()),'Screen touch pauses native playback')
    resume_point=tap(page,'播放'); time.sleep(.5)
    check(playing(),'Native play button resumes actual decoder from browser')
    click_fraction(page,*resume_point); time.sleep(.4)
    check(any(n.attrib.get('text')=='播放' for n in nodes()),'Native pause button works through preview touch coordinates')
    page.screenshot(path=str(report/('preview-player-v'+version+'.png')),full_page=True)
    (report/('player-douyin-v'+version+'.png')).write_bytes(adb('exec-out','screencap','-p'))
    # A vertical video enters actual immersive portrait, with every control hidden.
    tap(page,'全屏'); time.sleep(.8)
    page.wait_for_function('document.querySelector("#screen").naturalWidth < document.querySelector("#screen").naturalHeight')
    tree=nodes()
    check(not any(n.attrib.get('text') in ('播放','暂停','全屏','退出全屏','横屏') for n in tree),'Fullscreen removes all playback buttons while preserving portrait orientation')
    page.screenshot(path=str(report/('preview-portrait-fullscreen-v'+version+'.png')),full_page=True)
    click_fraction(page,.5,.5); time.sleep(.4)
    check(any(n.attrib.get('text')=='退出全屏' for n in nodes()),'Tap reveals fullscreen overlay controls')
    tap(page,'横屏'); time.sleep(.8)
    page.wait_for_function('document.querySelector("#screen").naturalWidth > document.querySelector("#screen").naturalHeight')
    dimensions=page.locator('#screen').evaluate('(img)=>({w:img.clientWidth,h:img.clientHeight,nw:img.naturalWidth,nh:img.naturalHeight})')
    check(abs(dimensions['w']/dimensions['h']-dimensions['nw']/dimensions['nh'])<.03,'Landscape display and touch coordinates use true screen aspect ratio')
    page.screenshot(path=str(report/('preview-landscape-v'+version+'.png')),full_page=True)
    tap(page,'退出全屏'); time.sleep(.7)
    page.wait_for_function('document.querySelector("#screen").naturalWidth < document.querySelector("#screen").naturalHeight')
    check(any(n.attrib.get('text')=='全屏' for n in nodes()),'Exit fullscreen restores original orientation and normal controls')
    page.locator('[data-key="back"]').click(); time.sleep(.7)
    page.set_viewport_size({'width':390,'height':844})
    check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Narrow preview has no horizontal overflow')
    check(not errors,'No preview JavaScript errors: '+str(errors))
    browser.close()
result={'version':version,'checks':checks,'result':'passed','scope':'Loopback-only bridge, real isolated Android 15 APK; share, resolution, internal play, pause, rotation and viewport layout; no physical phone'}
(report/('preview-test-v'+version+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
