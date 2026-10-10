"""Create a separate test-only instrumentation APK, signed with the local app certificate."""
import os
import subprocess
import zipfile
from pathlib import Path

root=Path(os.environ.get('SHIYING_BUILD_ROOT',str(Path(__file__).resolve().parents[2])))
sdk=root/'.android-build/sdk'; tools=sdk/'build-tools/35.0.1'; jar=sdk/'platforms/android-35/android.jar'
jdk=Path(os.environ.get('SHIYING_JDK','D:/PyCharm 2026.1.1/jbr')); work=root/'.android-build/native-checks'
classes=work/'classes'; dex=work/'dex'
for path in (work,classes,dex): path.mkdir(parents=True,exist_ok=True)
env=os.environ.copy(); env.update(JAVA_HOME=str(jdk),TEMP=str(root/'.tmp'),TMP=str(root/'.tmp'))
env['SHIYING_KEY_PASSWORD']=(root/'.android-build/private/signing-password.txt').read_text(encoding='utf-8')
def run(args):
    values=[str(args[0])]+[p.relative_to(root).as_posix() if isinstance(p,Path) and p.is_relative_to(root) else str(p) for p in args[1:]]
    subprocess.run(values,cwd=root,env=env,check=True)
manifest=work/'AndroidManifest.xml'
checks=('NativeMediaChecks','NativeUiChecks','NativePlatformChecks','NativeChannelsChecks','NativeSocialChecks','NativeNoLoginChecks','NativePlayerChecks','NativeAlbumChecks','NativeFullscreenChecks','NativeAudioChecks')
manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="cn.shiying.mobile.tests"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/><application android:label="ShiYing checks"/>'+''.join('<instrumentation android:name="cn.shiying.mobile.'+name+'" android:targetPackage="cn.shiying.mobile"/>' for name in checks)+'</manifest>',encoding='utf-8')
run([tools/'aapt2.exe','link','-o',work/'resources.apk','-I',jar,'--manifest',manifest])
classpath=str(jar)+os.pathsep+str(root/'.android-build/app-build/app-classes.jar')
run([jdk/'bin/javac.exe','--release','8','-encoding','UTF-8','-classpath',classpath,'-d',classes,*root.joinpath('android/tests').glob('Native*Checks.java')])
archive=work/'checks.jar'
with zipfile.ZipFile(archive,'w') as bundle:
    for path in classes.rglob('*.class'): bundle.write(path,path.relative_to(classes).as_posix())
run([jdk/'bin/java.exe','-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--min-api','26','--lib',jar,'--classpath',root/'.android-build/app-build/app-classes.jar','--output',dex,archive])
with zipfile.ZipFile(work/'resources.apk') as resources,zipfile.ZipFile(work/'unsigned.apk','w') as bundle:
    for item in resources.infolist(): bundle.writestr(item,resources.read(item))
    for path in dex.glob('*.dex'): bundle.write(path,path.name,compress_type=zipfile.ZIP_STORED)
run([tools/'zipalign.exe','-f','4',work/'unsigned.apk',work/'aligned.apk'])
run([jdk/'bin/java.exe','-jar',tools/'lib/apksigner.jar','sign','--ks',root/'.android-build/private/shiying-release.jks','--ks-pass','env:SHIYING_KEY_PASSWORD','--key-pass','env:SHIYING_KEY_PASSWORD','--out',work/'checks.apk',work/'aligned.apk'])
print('Test-only instrumentation APK ready')
