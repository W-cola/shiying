import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests
parser=argparse.ArgumentParser(description='Compile and run the Android core parser checks on the JVM.')
parser.add_argument('--links',type=Path,help='Optional private JSON array of live Xiaohongshu test URLs; never included in the source archive.')
parser.add_argument('--live-platforms',action='store_true',help='Also test publicly accessible Bilibili example URLs.')
args=parser.parse_args()
root=Path(__file__).resolve().parents[2]
work=root/'.android-build'/'core-tests'; work.mkdir(parents=True,exist_ok=True)
jar=work/'json-20250517.jar'
if not jar.exists():
    uri='https://repo.maven.apache.org/maven2/org/json/json/20250517/json-20250517.jar'
    response=requests.get(uri,timeout=40); response.raise_for_status(); jar.write_bytes(response.content)
jdk=Path(os.environ.get('SHIYING_JDK','D:/PyCharm 2026.1.1/jbr'))
classes=work/'classes'; classes.mkdir(exist_ok=True)
sources=[*root.joinpath('android/app/src/main/java/cn/shiying/mobile/core').glob('*.java'),root/'android/tests/CoreTests.java',root/'android/tests/XiaohongshuTests.java',root/'android/tests/PlatformTests.java']
subprocess.run([str(jdk/'bin/javac.exe'),'--release','8','-encoding','UTF-8','-classpath',str(jar),'-d',str(classes),*map(str,sources)],check=True)
proxy=urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
java_args=['-Dhttps.proxyHost='+proxy.hostname,'-Dhttps.proxyPort='+str(proxy.port)] if proxy.hostname else []
counts=[]
for name in ('CoreTests','XiaohongshuTests','PlatformTests'):
    command=[str(jdk/'bin/java.exe'),*java_args,'-cp',str(classes)+os.pathsep+str(jar),name]
    if name=='XiaohongshuTests' and args.links:
        if not args.links.is_file(): parser.error('--links JSON file does not exist')
        command.extend([str(args.links.resolve()),str(root/'android/verification/xhs-test.json')])
    if name=='PlatformTests' and args.live_platforms: command.append(str(root/'android/verification/platform-live-test.json'))
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
    print(result.stdout.strip())
    if result.stderr: print(result.stderr.strip())
    if result.returncode: raise SystemExit(result.returncode)
    counts.append(int(re.search(r'Passed (\d+)',result.stdout).group(1)))
report={'version':'1.5.0','core_checks':counts[0],'xiaohongshu_checks':counts[1],
        'platform_checks':counts[2],'total':sum(counts),'live_links_included':bool(args.links) or args.live_platforms,'result':'passed'}
(root/'android/verification/parser-test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
