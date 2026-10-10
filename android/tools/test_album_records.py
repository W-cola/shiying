"""Compile the actual album record projection on the JVM and test legacy/new batches."""
import json
import os
import re
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[2]
work=root/'.android-build/album-tests'; work.mkdir(parents=True,exist_ok=True)
jdk=Path(os.environ.get('SHIYING_JDK','D:/PyCharm 2026.1.1/jbr'))
jar=root/'.android-build/core-tests/json-20250517.jar'
subprocess.run([str(jdk/'bin/javac.exe'),'--release','8','-encoding','UTF-8','-classpath',str(jar),'-d',str(work),str(root/'android/app/src/main/java/cn/shiying/mobile/AlbumRecords.java'),str(root/'android/tests/AlbumRecordTests.java')],check=True)
result=subprocess.run([str(jdk/'bin/java.exe'),'-cp',str(work)+os.pathsep+str(jar),'cn.shiying.mobile.AlbumRecordTests'],check=True,capture_output=True,text=True,encoding='utf-8')
print(result.stdout)
report={'version':'1.5.1','checks':int(re.search(r'Passed (\d+)',result.stdout).group(1)),'result':'passed','scope':'actual pure-Java group projection, legacy filenames, caption inclusion, picture order, separate batches and untouched underlying file rows'}
(root/'android/verification/album-record-test-v1.5.1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
