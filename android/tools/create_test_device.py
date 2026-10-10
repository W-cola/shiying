import os
import subprocess
from pathlib import Path

root=Path(os.environ.get('SHIYING_BUILD_ROOT',str(Path(__file__).resolve().parents[2])))
sdk=root/'.android-build/sdk'
avd=root/'.android-build/avd'; avd.mkdir(parents=True,exist_ok=True)
jdk=Path(os.environ.get('SHIYING_JDK','D:/PyCharm 2026.1.1/jbr'))
env=os.environ.copy(); env.update(JAVA_HOME=str(jdk),ANDROID_HOME=str(sdk),ANDROID_SDK_ROOT=str(sdk),
    ANDROID_USER_HOME=str(root/'.android-build/android-user'),ANDROID_AVD_HOME=str(avd),TEMP=str(root/'.tmp'),TMP=str(root/'.tmp'))
subprocess.run([str(sdk/'cmdline-tools/latest/bin/avdmanager.bat'),'create','avd','--force','--name','shiying-test',
    '--package','system-images;android-35;google_apis;x86_64','--device','pixel_6','--path',str(avd/'shiying-test.avd')],
    input='no\n',text=True,env=env,check=True)
print('Isolated Android test device ready.')
