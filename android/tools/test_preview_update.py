"""Check the preview's real build/install workflow and preserve app code/data."""
import hashlib
import json
import re
import time
import zipfile
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
from preview_server import adb

root=Path(__file__).resolve().parents[2]
url='http://127.0.0.1:8787'
report=root/'android/verification'
build_info=json.loads((report/'build.json').read_text(encoding='utf-8')); version=build_info['version']; version_code=build_info['version_code']

def media_count():
    value=adb('shell','content','query','--uri','content://media/external/video/media','--projection','_id').decode('utf-8','replace')
    return len(re.findall(r'^Row:',value,re.MULTILINE))

def code_hashes():
    build=json.loads((report/'build.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(root/'dist'/build['apk']) as archive:
        return {name:hashlib.sha256(archive.read(name)).hexdigest() for name in ('classes.dex','resources.arsc')}

before=code_hashes(); videos=media_count()
adb('shell',"am start -W -n cn.shiying.mobile/.MainActivity -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT ''"); time.sleep(.7)
adb('shell','uiautomator','dump','/sdcard/shiying-update-before.xml')
before_hierarchy=adb('exec-out','cat','/sdcard/shiying-update-before.xml').decode('utf-8','replace')
completed=re.search(r'text="(\d+ 个)"',before_hierarchy).group(1)
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':960,'height':940})
    page.goto(url,wait_until='domcontentloaded')
    page.wait_for_function('document.querySelector("#screen").naturalWidth > 0')
    with page.expect_response(lambda response:response.url.endswith('/rebuild')) as response:
        page.locator('#build').click()
    assert response.value.status==200
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=requests.get(url+'/state',timeout=5).json()
        if not state['busy']: break
        time.sleep(.5)
    else: raise AssertionError('Build/install did not complete')
    assert state['ready'] and state['version']==version and '已连接' in state['status'],state
    assert code_hashes()==before,'Rebuild changed executable code unexpectedly'
    assert media_count()==videos and videos>0,'Reinstall failed to preserve gallery media'
    package=adb('shell','dumpsys','package','cn.shiying.mobile').decode('utf-8','replace')
    assert ('versionCode='+str(version_code)) in package and ('versionName='+version) in package
    assert '.MainActivity' in adb('shell','dumpsys','activity','activities').decode('utf-8','replace')
    adb('shell','uiautomator','dump','/sdcard/shiying-update-qa.xml')
    hierarchy=adb('exec-out','cat','/sdcard/shiying-update-qa.xml').decode('utf-8','replace')
    assert completed in hierarchy,'Prior completed download collections were not preserved'
    page.wait_for_timeout(1500)
    page.screenshot(path=str(report/('preview-ready-v'+version+'.png')),full_page=True)
    browser.close()
result={'version':version,'result':'passed','checks':7,'rebuild_install':'passed','previous_downloads':'preserved','completed_collections':completed,'gallery_videos':videos,'verified_code_hashes':before,'scope':'Real preview browser build button; signed APK compiled and installed on isolated emulator, no physical phone'}
(report/('preview-update-test-v'+version+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
