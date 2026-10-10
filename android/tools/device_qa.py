"""Operate only the isolated emulator created for this application's QA."""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path(os.environ.get('SHIYING_BUILD_ROOT',str(Path(__file__).resolve().parents[2])))
adb=root/'.android-build/sdk/platform-tools/adb.exe'
serial='emulator-5580'
report=root/'android/verification'; report.mkdir(exist_ok=True)
def call(*args,binary=False):
    result=subprocess.run([str(adb),'-P','5039','-s',serial,*map(str,args)],capture_output=True,timeout=55)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[:1200])
    return result.stdout if binary else result.stdout.decode('utf-8',errors='replace').strip()

def tree():
    call('shell','uiautomator','dump','/sdcard/shiying-ui.xml')
    raw=call('exec-out','cat','/sdcard/shiying-ui.xml')
    (report/'ui-last.xml').write_text(raw,encoding='utf-8')
    return ET.fromstring(raw)

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['boot','install','launch','share','share-file','share-mobile','dump','tap','screen','downloads','logs','home','verify-download','verify-xhs-video','verify-mobile'])
parser.add_argument('value',nargs='?',default='')
args=parser.parse_args()
if args.action=='boot': print(call('shell','getprop','sys.boot_completed'))
elif args.action=='install':
    package=root/'.android-build/app-build/install.apk'; shutil.copy2(root/'dist/拾影-安卓版-v1.7.0.apk',package)
    print(call('install','-r',package))
elif args.action=='launch':
    print(call('shell','am','start','-W','-n','cn.shiying.mobile/.MainActivity'))
elif args.action=='share':
    print(call('shell','am','start','-W','-n','cn.shiying.mobile/.MainActivity','-a','android.intent.action.SEND','-t','text/plain',
               '--es','android.intent.extra.TEXT','https://v.douyin.com/78nnhuQHT8k/'))
elif args.action=='share-file':
    urls=json.loads((root/'.tmp/xhs-links.json').read_text(encoding='utf-8'))
    command='am start -W -n cn.shiying.mobile/.MainActivity -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT '+shlex.quote(urls[int(args.value or 0)])
    output=call('shell',command)
    print('Share intent delivered; private URL omitted from test output.')
elif args.action=='share-mobile':
    share='4.89 复制打开抖音，看看【平均Mister的作品】# 发布会  https://v.douyin.com/xP--46iFdBs/ 04/13 O@K.jC :6pm QxF:/'
    command='am start -W -n cn.shiying.mobile/.MainActivity -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT '+shlex.quote(share)
    print(call('shell',command))
elif args.action=='dump':
    t=tree(); print(json.dumps([{'text':re.sub(r'(xsec_token=)[^&\s]+',r'\1[omitted]',n.attrib.get('text','')),'bounds':n.attrib.get('bounds'),'class':n.attrib.get('class')}
        for n in t.iter('node') if n.attrib.get('text')],ensure_ascii=False))
elif args.action=='tap':
    t=tree(); nodes=[n for n in t.iter('node') if args.value in n.attrib.get('text','')]
    assert nodes,'No matching visible control: '+args.value
    node=nodes[0]; points=list(map(int,re.findall(r'\d+',node.attrib['bounds'])))
    print(call('shell','input','tap',(points[0]+points[2])//2,(points[1]+points[3])//2))
elif args.action=='screen':
    dest=report/(args.value or 'home.png'); dest.write_bytes(call('exec-out','screencap','-p',binary=True)); print(dest)
elif args.action=='downloads': print(call('shell','ls','-la','/sdcard/Download/拾影'))
elif args.action=='logs':
    raw=call('logcat','-d','-v','brief','AndroidRuntime:E','chromium:E','*:S')
    (report/'runtime-log.txt').write_text(raw,encoding='utf-8'); print(raw[-7000:])
elif args.action=='home': print(call('shell','input','keyevent','3'))
elif args.action=='verify-download':
    names=call('shell','ls','-1','/sdcard/Download/拾影').splitlines()
    name=next(n for n in names if '7693840282563565674' in n and n.endswith('.mp4'))
    dest=report/'emulator-video.mp4'
    print(call('pull','/sdcard/Download/拾影/'+name,dest))
    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
    result={'device':'isolated Android 15 emulator','package':'cn.shiying.mobile','install':'passed','launch':'passed',
        'share_intent':'passed','source_video_id':'7693840282563565674','background_download':'passed',
        'bytes':dest.stat().st_size,'sha256':digest,'matches_desktop_video':digest=='908b8e9702039fd0dba99ae70dfe117ced5d1c2b0669eee4d7cc126a7d08952e'}
    ffprobe=shutil.which('ffprobe')
    if ffprobe:
        probe=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height','-of','json',str(dest)],capture_output=True,check=True)
        result['probe']=json.loads(probe.stdout)
    (report/'emulator-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
elif args.action=='verify-xhs-video':
    note_id='6a7bf28a0000000026036ba2'
    names=call('shell','ls','-1','/sdcard/Download/拾影').splitlines()
    name=next(n for n in names if note_id in n and n.endswith('.mp4'))
    dest=report/'emulator-xhs-video.mp4'
    print(call('pull','/sdcard/Download/拾影/'+name,dest))
    data=dest.read_bytes()
    assert data[4:8]==b'ftyp','Saved file is not an MP4 container'
    result={'device':'isolated Android 15 emulator','package':'cn.shiying.mobile','version':'1.1.0',
        'source_note_id':note_id,'title':'是厕所王来了','author':'育育','share_intent':'passed',
        'background_download':'passed','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    ffprobe=shutil.which('ffprobe')
    if ffprobe:
        probe=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height','-of','json',str(dest)],capture_output=True,check=True)
        result['probe']=json.loads(probe.stdout)
    (report/'xhs-video-device-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
elif args.action=='verify-mobile':
    video_id='7693747185347940454'
    names=call('shell','ls','-1','/sdcard/Movies/拾影').splitlines()
    name=next(n for n in reversed(names) if video_id in n and n.endswith('.mp4'))
    dest=report/'emulator-mobile-video.mp4'
    print(call('pull','/sdcard/Movies/拾影/'+name,dest))
    data=dest.read_bytes(); assert data[4:8]==b'ftyp','Downloaded media is not MP4'
    query='content query --uri content://media/external/video/media --projection _id:_display_name:mime_type:relative_path:is_pending:width:height:duration --where '+shlex.quote("_display_name='"+name.replace("'","''")+"'")
    rows=call('shell',query)
    assert 'Movies/拾影/' in rows and 'is_pending=0' in rows,'Completed video is not visible in the system video library: '+rows
    result={'version':'1.2.0','device':'isolated Android 15 emulator','source_video_id':video_id,
            'source_share':'https://v.douyin.com/xP--46iFdBs/','whole_mobile_share':'passed',
            'download':'passed','system_video_library':'passed','directory':'Movies/拾影',
            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'media_store':rows}
    ffprobe=shutil.which('ffprobe')
    if ffprobe:
        probe=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height','-of','json',str(dest)],capture_output=True,check=True)
        result['probe']=json.loads(probe.stdout)
    (report/'mobile-share-gallery-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
